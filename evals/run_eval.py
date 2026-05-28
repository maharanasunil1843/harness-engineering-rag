"""RAGAS evaluation harness for the harness engineering RAG system.

Loads the golden set, calls ask() for each query, evaluates with RAGAS metrics
(faithfulness, context_precision_without_reference, answer_relevancy), and exits
non-zero if mean faithfulness drops below 0.85.

Usage:
    uv run python -m evals.run_eval          # full 20-query eval
    uv run python -m evals.run_eval --quick  # first 5 queries only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Monkey-patch the langchain_community module that was removed in 0.4.x
# but is still imported by ragas 0.4.3.
import unittest.mock as _mock

if "langchain_community.chat_models.vertexai" not in sys.modules:
    sys.modules["langchain_community.chat_models.vertexai"] = _mock.MagicMock()

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from anthropic import Anthropic  # noqa: E402
from openai import OpenAI  # noqa: E402
from ragas import EvaluationDataset, SingleTurnSample, evaluate  # noqa: E402
from ragas.embeddings.base import embedding_factory  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.metrics.collections import (  # noqa: E402
    AnswerRelevancy,
    ContextPrecisionWithoutReference,
    Faithfulness,
)

from app.agents import ask  # noqa: E402

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set" / "queries.json"
RESULTS_DIR = Path(__file__).parent / "results"
FAITHFULNESS_THRESHOLD = 0.85


def _load_queries(quick: bool) -> list[dict]:
    queries = json.loads(GOLDEN_SET_PATH.read_text())
    return queries[:5] if quick else queries


def _build_metrics() -> list:
    evaluator_llm = llm_factory(
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        client=Anthropic(),
    )
    evaluator_embeddings = embedding_factory(
        provider="openai",
        model="text-embedding-3-small",
        client=OpenAI(),
    )
    return [
        Faithfulness(llm=evaluator_llm),
        ContextPrecisionWithoutReference(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
    ]


async def _collect_samples(queries: list[dict]) -> list[tuple[dict, SingleTurnSample]]:
    samples: list[tuple[dict, SingleTurnSample]] = []
    for item in queries:
        print(f"  Querying: {item['query'][:70]}...")
        try:
            result = await ask(item["query"])
            contexts = [
                s.get("content", s.get("text", str(s)))
                for s in (result.sources or [])
                if s
            ]
            sample = SingleTurnSample(
                user_input=item["query"],
                response=result.answer,
                retrieved_contexts=contexts if contexts else ["No context retrieved."],
            )
        except Exception as exc:
            print(f"    [WARN] ask() failed for this query: {exc}")
            sample = SingleTurnSample(
                user_input=item["query"],
                response="Error: could not retrieve answer.",
                retrieved_contexts=["No context retrieved."],
            )
        samples.append((item, sample))
    return samples


def _print_table(rows: list[dict]) -> None:
    header = f"{'Query':<55} {'F':>6} {'CP':>6} {'AR':>6}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        q = r["query"][:52] + "..." if len(r["query"]) > 55 else r["query"]
        f = f"{r['faithfulness']:.3f}" if r["faithfulness"] is not None else "  N/A"
        cp = f"{r['context_precision']:.3f}" if r["context_precision"] is not None else "  N/A"
        ar = f"{r['answer_relevancy']:.3f}" if r["answer_relevancy"] is not None else "  N/A"
        print(f"{q:<55} {f:>6} {cp:>6} {ar:>6}")
    print()


def _save_results(rows: list[dict], aggregates: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "per_query": rows,
        "aggregates": aggregates,
    }
    path = RESULTS_DIR / "eval_results.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"Results saved to {path}")


def main(quick: bool = False) -> int:
    print(f"Loading golden set from {GOLDEN_SET_PATH}")
    queries = _load_queries(quick)
    print(f"Running eval on {len(queries)} queries {'(quick mode)' if quick else ''}\n")

    print("Collecting answers from ask()...")
    pairs = asyncio.run(_collect_samples(queries))

    golden_items = [p[0] for p in pairs]
    ragas_samples = [p[1] for p in pairs]

    print("\nRunning RAGAS evaluation...")
    metrics = _build_metrics()
    dataset = EvaluationDataset(samples=ragas_samples)
    result = evaluate(dataset=dataset, metrics=metrics, raise_exceptions=False)

    scores_df = result.to_pandas()

    rows: list[dict] = []
    for i, item in enumerate(golden_items):
        row_scores = scores_df.iloc[i] if i < len(scores_df) else {}
        rows.append(
            {
                "query": item["query"],
                "expected_intent": item["expected_intent"],
                "faithfulness": float(row_scores.get("faithfulness", float("nan")))
                if row_scores.get("faithfulness") is not None
                else None,
                "context_precision": float(
                    row_scores.get("context_precision_without_reference", float("nan"))
                )
                if row_scores.get("context_precision_without_reference") is not None
                else None,
                "answer_relevancy": float(row_scores.get("answer_relevancy", float("nan")))
                if row_scores.get("answer_relevancy") is not None
                else None,
                "response_preview": ragas_samples[i].response[:120] + "..."
                if len(ragas_samples[i].response) > 120
                else ragas_samples[i].response,
            }
        )

    _print_table(rows)

    f_vals = [r["faithfulness"] for r in rows if r["faithfulness"] is not None]
    cp_vals = [r["context_precision"] for r in rows if r["context_precision"] is not None]
    ar_vals = [r["answer_relevancy"] for r in rows if r["answer_relevancy"] is not None]

    aggregates = {
        "mean_faithfulness": sum(f_vals) / len(f_vals) if f_vals else None,
        "mean_context_precision": sum(cp_vals) / len(cp_vals) if cp_vals else None,
        "mean_answer_relevancy": sum(ar_vals) / len(ar_vals) if ar_vals else None,
        "query_count": len(rows),
    }

    print("Aggregate scores:")
    for k, v in aggregates.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    _save_results(rows, aggregates)

    mean_faith = aggregates["mean_faithfulness"]
    if mean_faith is not None and mean_faith < FAITHFULNESS_THRESHOLD:
        print(
            f"\nFAIL: mean faithfulness {mean_faith:.4f} < threshold {FAITHFULNESS_THRESHOLD}"
        )
        return 1

    print(f"\nPASS: mean faithfulness {mean_faith:.4f} >= threshold {FAITHFULNESS_THRESHOLD}" if mean_faith is not None else "\nWARN: no faithfulness scores computed")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation")
    parser.add_argument("--quick", action="store_true", help="Run only the first 5 queries")
    args = parser.parse_args()
    sys.exit(main(quick=args.quick))
