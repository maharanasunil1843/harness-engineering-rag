#!/usr/bin/env python3
"""Smoke test: verifies all external integrations are reachable before development."""
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def check(label: str, fn):
    try:
        result = fn()
        print(f"  {label}")
        return result
    except Exception as exc:
        print(f"  {label}")
        print(f"    ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


# (a) Postgres + pgvector
def check_postgres():
    import psycopg

    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url) as conn:
        row = conn.execute(
            "SELECT extname FROM pg_extension WHERE extname='vector'"
        ).fetchone()
        assert row is not None, "pgvector extension not found — run: CREATE EXTENSION vector;"
    return True


# (b) Anthropic LLM
def check_anthropic():
    import anthropic

    model = os.environ["WORKER_MODEL"]
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=model,
        max_tokens=20,
        messages=[{"role": "user", "content": "say ok"}],
    )
    text = msg.content[0].text
    print(f"    response: {text!r}")
    return text


# (c) OpenAI embeddings
def check_openai_embeddings():
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.embeddings.create(model="text-embedding-3-small", input="test")
    dim = len(resp.data[0].embedding)
    print(f"    embedding dim: {dim}")
    assert dim == 1536, f"Expected 1536, got {dim}"
    return dim


# (d) Upstash Redis round-trip
def check_upstash_redis():
    from upstash_redis import Redis

    redis = Redis(
        url=os.environ["UPSTASH_REDIS_REST_URL"],
        token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
    )
    redis.set("smoke", "ok")
    val = redis.get("smoke")
    assert val == "ok", f"Expected 'ok', got {val!r}"
    return val


# (e) LangSmith key present
def check_langsmith():
    key = os.environ.get("LANGSMITH_API_KEY", "")
    assert key, "LANGSMITH_API_KEY is not set or empty"
    return True


if __name__ == "__main__":
    print("Running smoke tests…\n")
    check("✅ (a) Postgres + pgvector", check_postgres)
    check("✅ (b) Anthropic LLM", check_anthropic)
    check("✅ (c) OpenAI embeddings", check_openai_embeddings)
    check("✅ (d) Upstash Redis round-trip", check_upstash_redis)
    check("✅ (e) LangSmith API key present", check_langsmith)
    print("\n🟢 All systems go.")
