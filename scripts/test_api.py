"""Test the FastAPI endpoints locally."""
import asyncio
import json
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = "http://localhost:8000"


async def main() -> None:
    async with httpx.AsyncClient(timeout=120.0) as c:
        # Health check
        r = await c.get(f"{BASE}/api/health")
        print(f"Health: {r.status_code} — {r.json()['status']}")
        assert r.status_code == 200

        # Non-streaming query
        print("\n--- Non-streaming query ---")
        t0 = time.perf_counter()
        r = await c.post(f"{BASE}/api/query", json={"query": "What is a harness?"})
        elapsed = (time.perf_counter() - t0) * 1000
        data = r.json()
        print(f"Status: {r.status_code}")
        print(f"Answer: {data['answer'][:200]}...")
        print(f"Sources: {len(data['sources'])}")
        print(f"Confidence: {data['confidence']}")
        print(f"Latency: {elapsed:.0f}ms")
        print(f"Cache hit: {data['cache_hit']}")

        # SSE streaming query
        print("\n--- Streaming query ---")
        async with c.stream(
            "POST",
            f"{BASE}/api/query/stream",
            json={"query": "How do hooks work as an enforcement layer?"},
        ) as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    raw = line[6:]
                    try:
                        event_data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event_data, dict) and "step" in event_data:
                        print(f"  [status] {event_data['step']}")
                    elif isinstance(event_data, dict) and "text" in event_data:
                        print(event_data["text"], end="", flush=True)
                    elif isinstance(event_data, dict) and "answer" in event_data:
                        print(f"\n  [done] confidence={event_data['confidence']}")

        # Cache stats
        r = await c.get(f"{BASE}/api/cache/stats")
        print(f"\nCache stats: {r.json()}")

        print("\n✅ All API tests passed.")


asyncio.run(main())
