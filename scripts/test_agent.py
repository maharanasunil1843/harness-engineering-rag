"""Integration test for the agentic core — all routing paths + cache."""
import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

from app.agents import ask  # noqa: E402
from app.retrieval.cache import cache_stats  # noqa: E402

queries = [
    # Retrieval path
    ("What is a harness in the context of AI agents?", "retrieval"),
    # SQL path
    ("List all harness components in the safety category", "sql"),
    # Hybrid path
    ("What failure modes do hooks address, and what's the principle behind them?", "hybrid"),
    # Direct path
    ("Hello, what can you help me with?", "direct"),
    # Cross-doc synthesis
    ("How does Red Hat's two-phase workflow relate to the planner/evaluator pattern described by Anthropic?", "retrieval"),
    # Surfaces YOUR production system from the DOCX
    ("How are harness engineering principles applied in a manufacturing enterprise?", "retrieval"),
    # Cache hit test — repeat query 1
    ("What is a harness in the context of AI agents?", "cache_hit"),
]


async def main() -> None:
    for q, expected in queries:
        print(f"\n{'=' * 70}")
        print(f"Q: {q}")
        print(f"Expected: {expected}")
        t0 = time.perf_counter()
        result = await ask(q)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"Answer: {result.answer[:500]}...")
        print(f"Sources: {len(result.sources)}")
        print(f"Confidence: {result.confidence}")
        print(f"Trace: {result.trace_id}")
        print(f"Latency: {elapsed:.0f}ms")

    stats = await cache_stats()
    print(f"\n{'=' * 70}")
    print(f"Cache stats: {stats}")
    print("Expected: at least 1 hit (query 7 = repeat of query 1)")


asyncio.run(main())
