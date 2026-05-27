"""Database client: idempotent upserts for documents and chunks."""
import hashlib
import json
import os
from uuid import UUID, uuid4

import psycopg
from pgvector.psycopg import register_vector

from ingestion.chunker import Chunk
from ingestion.elements import ParsedDoc


def _get_conn() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def _doc_hash(parsed: ParsedDoc) -> str:
    raw = json.dumps(
        {
            "source_path": parsed.source_path,
            "title": parsed.title,
            "doc_type": parsed.doc_type,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def upsert_document(parsed: ParsedDoc) -> UUID:
    content_hash = _doc_hash(parsed)
    with _get_conn() as conn:
        # Check if already exists
        row = conn.execute(
            "SELECT doc_id FROM documents WHERE content_hash = %s",
            (content_hash,),
        ).fetchone()
        if row:
            return UUID(str(row[0]))

        new_id = uuid4()
        conn.execute(
            """
            INSERT INTO documents (doc_id, title, source_path, doc_type, author, published, page_count, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s::date, %s, %s)
            """,
            (
                str(new_id),
                parsed.title,
                parsed.source_path,
                parsed.doc_type,
                parsed.author,
                parsed.published,
                parsed.page_count,
                content_hash,
            ),
        )
        conn.commit()
        return new_id


def upsert_chunks(doc_id: UUID, chunks: list[Chunk]) -> None:
    if not chunks:
        return

    with _get_conn() as conn:
        # Fetch existing content_hashes for this doc to skip duplicates
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT content_hash FROM chunks WHERE doc_id = %s",
                (str(doc_id),),
            ).fetchall()
        }

        new_chunks = [c for c in chunks if c.content_hash not in existing]
        if not new_chunks:
            print(f"  All {len(chunks)} chunks already in DB — skipping.")
            return

        with conn.cursor() as cur:
            for chunk in new_chunks:
                if chunk.embedding is None:
                    raise ValueError(f"Chunk {chunk.chunk_id} has no embedding — call embed_chunks first")
                raw = json.dumps(chunk.raw_content) if chunk.raw_content else None
                meta = json.dumps(chunk.metadata)
                cur.execute(
                    """
                    INSERT INTO chunks
                        (chunk_id, doc_id, parent_chunk_id, element_type, content,
                         raw_content, metadata, embedding, content_hash)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                    ON CONFLICT (chunk_id) DO NOTHING
                    """,
                    (
                        str(chunk.chunk_id),
                        str(doc_id),
                        str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
                        chunk.element_type,
                        chunk.content,
                        raw,
                        meta,
                        chunk.embedding,
                        chunk.content_hash,
                    ),
                )
        conn.commit()
        print(f"  Inserted {len(new_chunks)} new chunks ({len(chunks) - len(new_chunks)} skipped).")
