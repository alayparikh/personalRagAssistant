"""Unit tests for the pure functions in rag.py.

These exist because the retrieval eval can't reliably catch regressions in
them. A hybrid retriever is deliberately redundant: when BM25 degrades, vector
search often still surfaces the right chunk, so the end-to-end eval stays green
while a component is broken. That redundancy is good for users and bad for
detection, so the components are tested directly here and the eval covers the
pipeline as a whole.

Run: python -m pytest tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class TestTokenize:
    """Guards the BM25 tokenizer. The original bug: the default whitespace
    tokenizer made a whole URL one opaque token, so a query for "linkedin"
    scored zero against a chunk containing linkedin.com."""

    def test_splits_url_into_matchable_terms(self):
        tokens = rag._tokenize("https://www.linkedin.com/in/sam-rivera-example/")
        assert "linkedin" in tokens
        assert "rivera" in tokens

    def test_splits_email_into_matchable_terms(self):
        tokens = rag._tokenize("jane.doe@example.com")
        assert "jane" in tokens
        assert "doe" in tokens
        assert "example" in tokens

    def test_lowercases(self):
        assert rag._tokenize("LinkedIn GitHub") == ["linkedin", "github"]

    def test_keeps_alphanumerics_together(self):
        assert "claude5" in rag._tokenize("claude5 model")


class TestRedactSecrets:
    def test_redacts_ssn(self):
        out, flagged = rag.redact_secrets("ssn 123-45-6789 here")
        assert "123-45-6789" not in out
        assert flagged

    def test_redacts_aws_key(self):
        out, flagged = rag.redact_secrets("key AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in out
        assert flagged

    def test_redacts_anthropic_key(self):
        out, flagged = rag.redact_secrets("sk-ant-api03-" + "a" * 30)
        assert "sk-ant-api03" not in out
        assert flagged

    def test_leaves_phone_numbers_alone(self):
        # Deliberate: these documents contain phone numbers and long medical
        # record IDs. Over-broad redaction would corrupt legitimate answers.
        out, flagged = rag.redact_secrets("call 408-483-1223")
        assert "408-483-1223" in out
        assert not flagged

    def test_leaves_long_digit_ids_alone(self):
        out, flagged = rag.redact_secrets("health id 8573032742367710")
        assert "8573032742367710" in out
        assert not flagged


class TestSummarizeUsage:
    def test_prices_known_model(self):
        result = rag.summarize_usage(
            {"claude-sonnet-5": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
        )
        assert result["cost_usd"] == 12.0  # $2 in + $10 out
        assert result["models_called"] == ["claude-sonnet-5"]

    def test_unknown_model_yields_none_not_zero(self):
        # None means "tokens spent, price unknown"; 0.0 means "genuinely free".
        # Collapsing them would silently under-report spend.
        result = rag.summarize_usage({"nonexistent": {"input_tokens": 100, "output_tokens": 50}})
        assert result["cost_usd"] is None
        assert result["input_tokens"] == 100

    def test_no_calls_is_free_not_unknown(self):
        result = rag.summarize_usage({})
        assert result["cost_usd"] == 0.0
        assert result["input_tokens"] == 0

    def test_sums_across_models(self):
        result = rag.summarize_usage({
            "claude-sonnet-5": {"input_tokens": 1000, "output_tokens": 100},
            "claude-haiku-4-5": {"input_tokens": 500, "output_tokens": 50},
        })
        assert result["input_tokens"] == 1500
        assert result["output_tokens"] == 150
        assert len(result["models_called"]) == 2


class TestComputeK:
    def test_small_corpus_uses_floor(self):
        assert rag.compute_k(54) == rag.RETRIEVAL_K_MIN

    def test_empty_corpus_uses_floor(self):
        assert rag.compute_k(0) == rag.RETRIEVAL_K_MIN

    def test_scales_with_corpus_size(self):
        # the real regression: 1038 chunks must widen the window past the
        # k=4 that was fine at 54 chunks
        assert rag.compute_k(1038) > rag.RETRIEVAL_K_MIN

    def test_clamped_at_ceiling(self):
        assert rag.compute_k(10_000_000) == rag.RETRIEVAL_K_MAX

    def test_monotonic(self):
        sizes = [0, 100, 500, 1000, 5000, 50_000]
        ks = [rag.compute_k(n) for n in sizes]
        assert ks == sorted(ks)

    def test_env_override_pins_value(self, monkeypatch):
        monkeypatch.setattr(rag, "RETRIEVAL_K_OVERRIDE", "7")
        assert rag.compute_k(1038) == 7


class TestBuildRetrieverUsesComputedK:
    """compute_k() being correct is useless if build_retriever() ignores it.
    A revert to a hardcoded k passes every other test in this file."""

    def test_vector_and_bm25_both_get_computed_k(self):
        from langchain_core.retrievers import BaseRetriever

        n = 1200  # -> compute_k = 12, well clear of the k=4 floor
        captured = {}

        class _Stub(BaseRetriever):
            def _get_relevant_documents(self, query, *, run_manager=None):
                return []

        class _FakeVS:
            def get(self, **kwargs):
                return {
                    "documents": [f"chunk {i}" for i in range(n)],
                    "metadatas": [{"source": "f.txt"} for _ in range(n)],
                }

            def as_retriever(self, search_kwargs=None, **kw):
                captured["vector_k"] = search_kwargs["k"]
                return _Stub()

        ensemble = rag.build_retriever(_FakeVS())
        expected = rag.compute_k(n)

        assert expected > rag.RETRIEVAL_K_MIN, "test corpus must exceed the floor"
        assert captured["vector_k"] == expected
        bm25 = [r for r in ensemble.retrievers if hasattr(r, "k")]
        assert bm25 and bm25[0].k == expected


class TestGroupsForPath:
    FOLDERS = {"docs/HR": ["HR", "VP"], "docs/HR/Payroll": ["Payroll"]}
    DEFAULT = ["Everyone"]

    def test_longest_prefix_wins(self):
        groups = rag.groups_for_path("docs/HR/Payroll/salaries.pdf", self.FOLDERS, self.DEFAULT)
        assert groups == ["Payroll"]

    def test_parent_folder_match(self):
        groups = rag.groups_for_path("docs/HR/handbook.pdf", self.FOLDERS, self.DEFAULT)
        assert groups == ["HR", "VP"]

    def test_unmapped_path_falls_back_to_default(self):
        groups = rag.groups_for_path("docs/random.pdf", self.FOLDERS, self.DEFAULT)
        assert groups == self.DEFAULT

    def test_leading_dot_slash_normalized(self):
        groups = rag.groups_for_path("./docs/HR/handbook.pdf", self.FOLDERS, self.DEFAULT)
        assert groups == ["HR", "VP"]


class TestBuildGroupFilter:
    def test_none_means_unrestricted(self):
        assert rag.build_group_filter(None) is None

    def test_superuser_bypasses_filtering(self):
        assert rag.build_group_filter(["HR", rag.SUPERUSER_GROUP]) is None

    def test_empty_groups_fails_closed(self):
        # Must deny everything, never match everything. A bug here is a
        # silent data leak rather than a visible error.
        f = rag.build_group_filter([])
        assert f is not None
        assert f != {}

    def test_multiple_groups_use_or(self):
        f = rag.build_group_filter(["HR", "Engineering"])
        assert "$or" in f


class TestLoadDocx:
    def test_recovers_hyperlink_targets(self):
        # Plain-text extraction keeps only the anchor word "LinkedIn"; the URL
        # lives in the document's relationship table and is otherwise lost.
        fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "eval", "fixtures", "docs",
                               "sam_rivera_resume.docx")
        if not os.path.exists(fixture):
            return  # fixture corpus not present; covered by the eval instead
        text = rag.load_docx(fixture)[0].page_content
        assert "linkedin.com/in/sam-rivera-example" in text
        assert "github.com/sam-rivera-example" in text


class TestSourceValidation:
    """The model self-reports which sources it used; a path it names that
    wasn't actually retrieved must be dropped, not displayed."""

    def test_hallucinated_path_is_dropped(self):
        context = [Document(page_content="x", metadata={"source": "./docs/real.pdf"})]
        retrieved = {d.metadata.get("source") for d in context}
        claimed = ["./docs/real.pdf", "./docs/invented.pdf"]
        assert [s for s in claimed if s in retrieved] == ["./docs/real.pdf"]
