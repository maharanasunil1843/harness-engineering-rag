"""Batched OpenAI embedding with retry and cost tracking."""
import os

import tiktoken
from openai import OpenAI, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.chunker import Chunk

_COST_PER_MILLION = 0.02  # text-embedding-3-small


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry_error_cls=(RateLimitError,),  # type: ignore[arg-type]
)
def _embed_batch(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def embed_chunks(chunks: list[Chunk], batch_size: int = 64) -> list[Chunk]:
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    client = OpenAI()
    enc = tiktoken.get_encoding("cl100k_base")

    total = len(chunks)
    total_tokens = 0
    embedded = 0

    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c.content for c in batch]
        batch_tokens = sum(len(enc.encode(t)) for t in texts)

        vectors = _embed_batch(client, model, texts)

        for chunk, vec in zip(batch, vectors):
            chunk.embedding = vec

        total_tokens += batch_tokens
        embedded += len(batch)
        cost = (total_tokens / 1_000_000) * _COST_PER_MILLION
        print(f"  Embedded {embedded}/{total} chunks (cost so far: ~${cost:.4f})")

    return chunks
