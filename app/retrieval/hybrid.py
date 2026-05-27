"""Hybrid retrieval: dense (pgvector) + sparse (tsvector) fused with RRF."""
import json
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings
from app.observability.tracing import traced

_RRF_K = 60
_DENSE_FETCH = 20
_SPARSE_FETCH = 20


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    element_type: str
    raw_content: dict[str, Any] | None
    metadata: dict[str, Any]
    score: float
    rank_source: str


def _get_conn() -> psycopg.Connection:
    conn = psycopg.connect(get_settings().database_url)
    register_vector(conn)
    return conn


def _embed_query(query: str) -> list[float]:
    s = get_settings()
    client = OpenAI(api_key=s.openai_api_key)
    resp = client.embeddings.create(model=s.embedding_model, input=query)
    return resp.data[0].embedding


def _rrf_score(ranks: list[int]) -> float:
    return sum(1.0 / (_RRF_K + r) for r in ranks)


@traced("hybrid_retrieve")
async def hybrid_retrieve(
    query: str,
    top_k: int = 10,
    metadata_filter: dict | None = None,
    query_embedding: list[float] | None = None,
) -> list[RetrievedChunk]:
    # Embed query (skip if caller already did it)
    if query_embedding is None:
        query_embedding = _embed_query(query)

    meta_json = json.dumps(metadata_filter) if metadata_filter else None

    with _get_conn() as conn:
        # ── Dense retrieval ────────────────────────────────────────────────
        dense_rows = conn.execute(
            """
            SELECT chunk_id, doc_id, content, element_type, raw_content, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE (%s::jsonb IS NULL OR metadata @> %s::jsonb)
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_embedding, meta_json, meta_json, query_embedding, _DENSE_FETCH),
        ).fetchall()

        # ── Sparse retrieval ───────────────────────────────────────────────
        sparse_rows = conn.execute(
            """
            SELECT chunk_id, doc_id, content, element_type, raw_content, metadata,
                   ts_rank_cd(tsv, plainto_tsquery('english', %s)) AS score
            FROM chunks
            WHERE tsv @@ plainto_tsquery('english', %s)
              AND (%s::jsonb IS NULL OR metadata @> %s::jsonb)
            ORDER BY score DESC
            LIMIT %s
            """,
            (query, query, meta_json, meta_json, _SPARSE_FETCH),
        ).fetchall()

    # ── RRF fusion ────────────────────────────────────────────────────────
    # chunk_id -> {rank_in_dense, rank_in_sparse, row_data}
    rrf_map: dict[str, dict] = {}

    for rank, row in enumerate(dense_rows, start=1):
        cid = str(row[0])
        rrf_map[cid] = {
            "row": row,
            "dense_rank": rank,
            "sparse_rank": None,
            "source": "dense",
        }

    for rank, row in enumerate(sparse_rows, start=1):
        cid = str(row[0])
        if cid in rrf_map:
            rrf_map[cid]["sparse_rank"] = rank
            rrf_map[cid]["source"] = "hybrid"
        else:
            rrf_map[cid] = {
                "row": row,
                "dense_rank": None,
                "sparse_rank": rank,
                "source": "sparse",
            }

    scored: list[tuple[float, str, dict]] = []
    for cid, info in rrf_map.items():
        ranks = []
        if info["dense_rank"] is not None:
            ranks.append(info["dense_rank"])
        if info["sparse_rank"] is not None:
            ranks.append(info["sparse_rank"])
        score = _rrf_score(ranks)
        scored.append((score, cid, info))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    # ── Parent-chunk expansion ────────────────────────────────────────────
    parent_ids: set[str] = set()
    for _, _, info in top:
        row = info["row"]
        meta = row[5] if isinstance(row[5], dict) else {}
        parent_id = meta.get("parent_chunk_id")
        if parent_id:
            parent_ids.add(str(parent_id))

    # Remove parent IDs already in results
    existing_ids = {cid for _, cid, _ in top}
    parent_ids -= existing_ids

    parent_chunks: list[RetrievedChunk] = []
    if parent_ids:
        with _get_conn() as conn:
            placeholders = ",".join(["%s"] * len(parent_ids))
            parent_rows = conn.execute(
                f"SELECT chunk_id, doc_id, content, element_type, raw_content, metadata FROM chunks WHERE chunk_id IN ({placeholders})",  # noqa: S608
                list(parent_ids),
            ).fetchall()
        for pr in parent_rows:
            raw = pr[4]
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = None
            meta = pr[5] if isinstance(pr[5], dict) else {}
            parent_chunks.append(
                RetrievedChunk(
                    chunk_id=str(pr[0]),
                    doc_id=str(pr[1]),
                    content=pr[2],
                    element_type=pr[3],
                    raw_content=raw,
                    metadata=meta,
                    score=0.0,
                    rank_source="parent_expansion",
                )
            )

    # ── Build result list ──────────────────────────────────────────────────
    results: list[RetrievedChunk] = []
    for rrf, cid, info in top:
        row = info["row"]
        raw = row[4]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None
        meta = row[5] if isinstance(row[5], dict) else {}
        results.append(
            RetrievedChunk(
                chunk_id=cid,
                doc_id=str(row[1]),
                content=row[2],
                element_type=row[3],
                raw_content=raw,
                metadata=meta,
                score=rrf,
                rank_source=info["source"],
            )
        )

    return results + parent_chunks
