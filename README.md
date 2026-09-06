# RAG Assistant

Chat with your own PDFs/Word/text files. Embeddings run locally (free); only answer generation calls Claude.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in the project root:

```
ANTHROPIC_API_KEY=your-key-here
```

Get a key at https://console.anthropic.com/. `.env` is git-ignored — never commit it.

## Run

Drop `.pdf`, `.docx`, `.txt`, or `.md` files into `docs/` (auto-created on first run), then:

```bash
python rag.py                   # web chat UI at localhost:8501
python rag.py --cli             # terminal chat instead
python rag.py --cli --reindex   # force a full rebuild of the index
```

First run embeds everything into `chroma_db/`. Later runs only re-embed files that are **new or changed** — edit a file, hit **Sync documents** in the sidebar, no restart needed.

## Architecture

**Ingest** (local, no API calls):

```
docs/ → discover_files() → file_hash() vs manifest.json (skip unchanged)
      → load_file() → split_documents() (1000 chars, 200 overlap)
      → tag chunks with ACL groups → local MiniLM embeddings → Chroma
```

**Query** (only Claude usage):

```
question → answer_question()          ← every guardrail lives here
   ├ length cap                        reject before any API call
   ├ history-aware retriever           LLM call only if chat history exists
   │    └ EnsembleRetriever = vector (k) + BM25 keyword (k), k scales with corpus
   ├ empty context? → short-circuit, never calls Claude
   ├ structured-output answer → claude-sonnet-5
   ├ validate sources_used ⊆ retrieved, redact secrets
   └ log to logs/events.jsonl
```

`answer_question()` is the single entry point for both the CLI and web UI, so guardrails apply everywhere by construction.

| File | Role |
|---|---|
| `rag.py` | The engine — ingest, index, retrieve, guardrails, CLI, launcher |
| `app.py` | Streamlit UI + per-session rate limiting (thin; logic lives in `rag.py`) |
| `eval/run_eval.py` | Golden-set eval runner; exits non-zero on failure (CI-ready) |
| `permissions.yaml` | Folder → group ACL map (committed) |
| `users.yaml` | Logins + groups (git-ignored; RBAC currently dormant) |

**Adaptive retrieval breadth.** `k` is derived from corpus size (`compute_k()`), not hardcoded — roughly +1 per 100 chunks, clamped to 4–20, overridable with `RAG_RETRIEVAL_K`. A fixed `k=4` was fine at 54 chunks (the top 7% of the corpus) but silently starved recall at 1,038 chunks (top 0.4%): a document listing every employee stopped being retrieved for "how many employees are there", and the assistant correctly refused rather than guessing. Wider retrieval costs more per question — measured ~$0.011 → ~$0.020 — which is the deliberate tradeoff.

**Notable implementation details:** `.docx` hyperlinks are recovered from the document's relationship table (plain-text extraction drops the URL and keeps only anchor text like "LinkedIn"). BM25 uses a custom regex tokenizer — the default splits on whitespace, making a whole URL one unmatchable token.

## Configuration

| What | Where |
|---|---|
| `ANTHROPIC_API_KEY` | `.env` — required, exits without it |
| Your documents | `docs/` |
| `MODEL` | `rag.py` — defaults to `claude-sonnet-5` |
| `EMBEDDING_MODEL` | `rag.py` — defaults to `all-MiniLM-L6-v2` (small, no GPU) |

## Guardrails

All enforced inside `answer_question()`:

- **Input length cap** (2000 chars) — rejected before retrieval or any API call.
- **Prompt-injection resistance** — retrieved content is wrapped in `<retrieved_context>` tags and explicitly framed as untrusted data, not instructions.
- **Empty-context short-circuit** — zero retrieved chunks means the LLM is never called. Fires only on a genuinely empty result set (e.g. ACLs filtered everything out), not on retrieved-but-irrelevant content.
- **Typed error handling** — auth/rate-limit/timeout/connection failures each get a distinct message instead of a raw traceback.
- **Secret redaction** — narrow, high-precision patterns only (AWS keys, API keys, SSN format). A generic "long number" pattern would false-positive on medical record IDs and phone numbers.
- **Source attribution** — the "Sources" footer lists only files Claude reports actually using, via a `sources_used` schema field (`with_structured_output`), validated against what was retrieved. A plain text-instruction version of this was tried first and proved unreliable — the model dropped it on longer answers.
- **Rate limiting** (web UI only) — 30 questions/hour per session. In-memory; multi-instance needs Redis.

## Logging

Every request appends a JSON line to `logs/events.jsonl` (rotating, ~50MB ceiling):

```json
{"ts": 1788..., "question_len": 34, "num_sources": 7, "num_sources_used": 2,
 "sources_retrieved": ["./docs/a.pdf", "./docs/b.docx"], "sources_used": ["./docs/b.docx"],
 "guardrail": null, "latency_ms": 4633, "input_tokens": 4053, "output_tokens": 255,
 "cost_usd": 0.010656, "models_called": ["claude-sonnet-5"]}
```

Token counts come from a `get_usage_metadata_callback()` wrapping the whole pipeline, so they include the **query-rewrite call** that fires on follow-up turns — a first question costs one API call, every follow-up costs two. `cost_usd` is `0.0` when a guardrail short-circuited before any API call, and `null` when tokens were spent on a model absent from `PRICING` (never silently priced at zero).

Source **paths** are logged, never chunk text — the log file isn't access-controlled.

## Evals

`eval/golden_set.yaml` holds test questions grounded in your actual `docs/` content — fact lookups, out-of-scope negatives (should refuse), a multi-turn follow-up, and a prompt-injection attempt. Git-ignored; `eval/golden_set.example.yaml` is the schema template.

```bash
python -m pytest tests/ -q       # unit tests, fast, no API
python eval/run_eval.py          # retrieval-only, free — checks the right chunks were found
python eval/run_eval.py --live   # real API calls — checks generated answers
```

`--live` additionally verifies refusal and injection resistance. An `ERROR` (vs. `FAIL`) means the API call itself failed, not a quality regression. Update the golden set when you change `docs/` — a stale one gives false failures and false passes.

**Why both tests and evals.** A hybrid retriever is deliberately redundant: when BM25 degrades, vector search often still surfaces the right chunk. That's good for users and bad for detection — a deliberately broken `_tokenize()` was measured passing the full retrieval eval while `tests/test_units.py` caught it immediately. Evals cover the pipeline end to end; unit tests guard the components the pipeline can mask.

### CI

`.github/workflows/ci.yml` runs unit tests + the retrieval eval on every push and PR — no API key, no cost. It runs against the committed synthetic corpus in `eval/fixtures/` (not `docs/`, which is git-ignored), driven by the `RAG_DOCS_PATH` / `RAG_PERSIST_PATH` / `RAG_LOG_PATH` env overrides. The `--live` eval is a manual `workflow_dispatch` job, since it costs money and needs `ANTHROPIC_API_KEY` in repo secrets.

The fixture corpus is 30 chunks of deliberately competing content — several similar résumés plus engineering runbooks — because a small or semantically well-separated corpus lets every query retrieve everything, and an eval that can't fail is worse than no eval.

## Multi-user access control (built, currently disabled)

`rag.py` supports scoping documents by group, mirroring NAS-style folder ACLs (only HR sees `docs/HR/`). It's dormant — `app.py` calls `build_chain(vectorstore)` with no restriction, so all documents are visible with no login. To enable:

1. `cp users.yaml.example users.yaml` — set logins, passwords, and per-user groups.
2. Map folders to groups in `permissions.yaml`. `"ALL"` is a superuser group that bypasses filtering.
3. Add the `streamlit-authenticator` login gate to `app.py` and pass the user's groups into `build_chain(vectorstore, allowed_groups)`.
4. Run `--cli --reindex` after editing `permissions.yaml` — sync only re-tags files whose content changed.

Empty group list fails closed (denies everything), not open.

## Notes

- Indexing and retrieval are fully local — no API cost, no network call.
- Corpus size doesn't change per-question cost much: retrieval is always top-k, and k grows only slowly with the corpus. Cost scales mainly with query volume and conversation length.
- `venv/`, `chroma_db/`, `docs/`, `.env`, `users.yaml`, `logs/`, and `eval/golden_set.yaml` are git-ignored — a fresh clone starts clean.
