"""Golden-set eval runner.

Retrieval-only mode (default, no API cost): checks whether expected
keywords appear anywhere in the *retrieved chunks* for each question - a
cheap proxy for "was the right content found at all," and exactly the kind
of check that would have caught the BM25 tokenizer bug before it shipped.

Live mode (--live, calls the real Claude API, costs money): builds the
full chain and checks actual generated answers, including refusal/negative
and prompt-injection-resistance cases that retrieval alone can't verify.

Usage:
    python eval/run_eval.py                          # retrieval-only
    python eval/run_eval.py --live                    # full, real API calls
    python eval/run_eval.py --golden-set path/to.yaml
"""
import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

DEFAULT_GOLDEN_SET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_set.yaml")

REFUSAL_PHRASES = [
    "don't have", "do not have", "does not contain", "doesn't contain",
    "no information", "not mentioned", "cannot find", "can't find",
    "not available in", "not provided", "context does not",
    "don't know", "do not know", "can't share", "cannot share",
    "can't provide", "cannot provide", "won't share", "unable to",
    "not something i can",
]


def load_golden_set(path):
    if not os.path.exists(path):
        example = path.replace(".yaml", ".example.yaml")
        print(f"No golden set at {path}.")
        if os.path.exists(example):
            print(f"Copy {example} to {path} and edit it with real questions "
                  f"for your own docs/, then rerun.")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f) or []


def contains_any(text, keywords):
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def contains_all(text, keywords):
    lowered = text.lower()
    return all(k.lower() in lowered for k in keywords)


def looks_like_refusal(text):
    return any(p in text.lower() for p in REFUSAL_PHRASES)


def check_expectations(item, answer_text):
    if "expect_answer_contains_any" in item and not contains_any(answer_text, item["expect_answer_contains_any"]):
        return False, "missing expected keyword"
    if "expect_answer_contains_all" in item and not contains_all(answer_text, item["expect_answer_contains_all"]):
        return False, "missing one or more expected keywords"
    if "expect_answer_not_contains_any" in item and contains_any(answer_text, item["expect_answer_not_contains_any"]):
        return False, "answer leaked a forbidden phrase"
    if item.get("expect_refusal") and not looks_like_refusal(answer_text):
        return False, "expected a refusal/'don't know', got a confident answer"
    return True, ""


def run_retrieval_only(items, vectorstore):
    retriever = rag.build_retriever(vectorstore)
    results = []
    for item in items:
        if item.get("category") in ("multi-turn", "safety") or item.get("expect_refusal"):
            results.append((item["id"], "SKIP", "needs --live"))
            continue
        docs = retriever.invoke(item["question"])
        text = "\n".join(d.page_content for d in docs)
        ok, reason = check_expectations(item, text)
        results.append((item["id"], "PASS" if ok else "FAIL", reason))
    return results


def _grade(result_id, expectations, response):
    guardrail = response["guardrail"] or ""
    if guardrail.startswith("api_error"):
        return result_id, "ERROR", guardrail
    ok, reason = check_expectations(expectations, response["answer"])
    return result_id, "PASS" if ok else "FAIL", reason


def run_live(items, vectorstore):
    chain = rag.build_chain(vectorstore)
    results = []
    for item in items:
        if "turns" in item:
            history = []
            for i, turn in enumerate(item["turns"]):
                response = rag.answer_question(chain, turn["question"], history,
                                                 log_context={"mode": "eval"})
                results.append(_grade(f"{item['id']}#{i}", turn, response))
                history.extend([
                    HumanMessage(content=turn["question"]),
                    AIMessage(content=response["answer"]),
                ])
        else:
            response = rag.answer_question(chain, item["question"], [],
                                             log_context={"mode": "eval"})
            results.append(_grade(item["id"], item, response))
    return results


def print_report(results):
    width = max(len(r[0]) for r in results) + 2
    for id_, status, reason in results:
        marker = {"PASS": "✓", "FAIL": "✗", "SKIP": "-", "ERROR": "!"}[status]
        line = f"{marker} {status:5} {id_:<{width}} {reason}"
        print(line)

    passed = sum(1 for r in results if r[1] == "PASS")
    failed = sum(1 for r in results if r[1] == "FAIL")
    skipped = sum(1 for r in results if r[1] == "SKIP")
    errored = sum(1 for r in results if r[1] == "ERROR")
    print(f"\n{passed} passed, {failed} failed, {errored} errored, "
          f"{skipped} skipped ({len(results)} total)")
    return failed + errored


def main():
    parser = argparse.ArgumentParser(description="Run the golden-set eval")
    parser.add_argument("--live", action="store_true",
                        help="call the real Claude API and check generated answers "
                             "(costs money) instead of just checking retrieval")
    parser.add_argument("--golden-set", default=DEFAULT_GOLDEN_SET)
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    items = load_golden_set(args.golden_set)
    vectorstore = rag.get_vectorstore()
    if vectorstore is None:
        print("No documents indexed - run `python rag.py --cli --reindex` first.")
        return 1

    if args.live and not os.environ.get("ANTHROPIC_API_KEY"):
        print("--live requires ANTHROPIC_API_KEY to be set.")
        return 1

    print(f"Running {'LIVE (real API calls)' if args.live else 'retrieval-only'} "
          f"eval against {args.golden_set}\n")

    results = run_live(items, vectorstore) if args.live else run_retrieval_only(items, vectorstore)
    failed = print_report(results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
