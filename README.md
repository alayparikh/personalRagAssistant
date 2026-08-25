# RAG Assistant

Chat with your own PDFs/text/Word files using local embeddings + Claude for generation.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
# Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-key-here
```

Get a key at https://console.anthropic.com/. `.env` is git-ignored — never commit it.

## Add your documents

Drop `.pdf`, `.txt`, `.md`, or `.docx` files into `docs/` (created automatically on first run if missing). This repo's `docs/` folder is git-ignored, so your own files stay local.

## Run

```bash
python rag.py
```

Opens a chat UI in your browser at `http://localhost:8501`. First run embeds everything in `docs/` into a local vector store at `chroma_db/` (also git-ignored). Later runs only re-embed files that are new or changed — edit a file in `docs/`, click **Sync documents** in the sidebar, no restart needed.

### Terminal mode

```bash
python rag.py --cli
```

Same assistant, plain terminal chat instead of the browser UI. Type `quit`, `exit`, or `q` to stop.

Force a full rebuild (terminal mode only — the web UI's Sync button already picks up new/changed/deleted files automatically):

```bash
python rag.py --cli --reindex
```

## What you need to update

| What | Where | Why |
|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` (you create this) | Required — script exits immediately without it |
| Your documents | `docs/` | The assistant only knows what's in here |
| `MODEL` | `rag.py` | Swap the Claude model if you want a different one (defaults to `claude-sonnet-5`) |
| `EMBEDDING_MODEL` | `rag.py` | Local HuggingFace embedding model; default is `all-MiniLM-L6-v2` (small, fast, no GPU needed) |

Nothing else needs changing to run this out of the box.

## Multi-user access control (optional, currently disabled)

`rag.py` has built-in support for scoping documents by group — mirrors NAS-style folder ACLs (e.g. only HR can see `docs/HR/`) — but it's dormant by default: `app.py` calls `build_chain(vectorstore)` with no group restriction, so everyone who opens the app sees every document, no login required. This is meant for personal/single-user use.

To turn multi-user access control back on:

1. `cp users.yaml.example users.yaml` and edit it — logins, passwords, and each user's groups. It's git-ignored (streamlit-authenticator rewrites it with hashed passwords on first login).
2. Map department folders to groups in `permissions.yaml` (ships with an `HR`/`Engineering` example) — put files under `docs/HR/`, `docs/Engineering/`, etc. `"ALL"` is a superuser group that bypasses filtering entirely.
3. Re-add the `streamlit-authenticator` login gate to `app.py` and pass the logged-in user's groups into `build_chain(vectorstore, allowed_groups)`.
4. Run `python rag.py --cli --reindex` after any `permissions.yaml` change — sync only re-tags files that changed, not the whole index.

## Notes

- Embeddings run locally (`sentence-transformers`) — no API cost or network call for indexing/retrieval.
- Only chat responses call the Claude API and incur cost.
- `venv/`, `chroma_db/`, `docs/`, `.env`, and `users.yaml` are all git-ignored — a fresh clone starts clean.
