"""Section-aware chunker. Headings are solo chunks; text packs with overlap; tables/figures are never split."""
import hashlib
import json
import os
from typing import Any
from uuid import UUID, uuid4

import tiktoken
from anthropic import Anthropic
from pydantic import BaseModel

from ingestion.elements import Element


class Chunk(BaseModel):
    chunk_id: UUID
    parent_chunk_id: UUID | None
    element_type: str
    content: str
    raw_content: dict[str, Any] | None
    metadata: dict[str, Any]
    content_hash: str
    embedding: list[float] | None = None


def _encode(text: str, enc: tiktoken.Encoding) -> list[int]:
    return enc.encode(text)


def _hash(content: str, element_type: str, metadata: dict[str, Any]) -> str:
    sorted_meta = json.dumps(metadata, sort_keys=True)
    raw = f"{content}{element_type}{sorted_meta}"
    return hashlib.sha256(raw.encode()).hexdigest()


# In-process cache: content_hash -> summary string (survives across calls within one run)
_summary_cache: dict[str, str] = {}


def _summarize_table(content: str, content_hash: str) -> str:
    if content_hash in _summary_cache:
        return _summary_cache[content_hash]

    client = Anthropic()
    model = os.environ.get("WORKER_MODEL", "claude-haiku-4-5")
    msg = client.messages.create(
        model=model,
        max_tokens=80,
        messages=[
            {
                "role": "user",
                "content": (
                    "Write a one-sentence summary of this table for search indexing. "
                    "Be specific about what the table contains.\n\n" + content
                ),
            }
        ],
    )
    summary = msg.content[0].text.strip()
    _summary_cache[content_hash] = summary
    return summary


def _make_chunk(
    elements: list[Element],
    element_type: str,
    content: str,
    raw_content: dict[str, Any] | None,
    metadata: dict[str, Any],
    parent_chunk_id: UUID | None,
) -> Chunk:
    h = _hash(content, element_type, metadata)
    return Chunk(
        chunk_id=uuid4(),
        parent_chunk_id=parent_chunk_id,
        element_type=element_type,
        content=content,
        raw_content=raw_content,
        metadata=metadata,
        content_hash=h,
    )


def chunk_elements(
    elements: list[Element],
    target_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    enc = tiktoken.get_encoding("cl100k_base")
    chunks: list[Chunk] = []

    current_heading_id: UUID | None = None
    # Text accumulation buffer
    buf_elements: list[Element] = []
    buf_tokens: list[list[int]] = []

    def flush_text_buffer() -> None:
        nonlocal buf_elements, buf_tokens
        if not buf_elements:
            return

        # Pack buf into chunks of ≤ target_tokens with overlap
        all_toks: list[list[int]] = buf_tokens[:]
        all_elems: list[Element] = buf_elements[:]

        i = 0
        while i < len(all_toks):
            acc_toks: list[int] = []
            acc_elems: list[Element] = []
            j = i
            while j < len(all_toks) and len(acc_toks) + len(all_toks[j]) <= target_tokens:
                acc_toks += all_toks[j]
                acc_elems.append(all_elems[j])
                j += 1
            if not acc_elems:
                # Single element exceeds target — emit as-is
                acc_elems = [all_elems[i]]
                acc_toks = all_toks[i]
                j = i + 1

            content = " ".join(e.content for e in acc_elems)
            metadata = acc_elems[0].metadata.copy()
            h = _hash(content, "text", metadata)
            chunks.append(
                Chunk(
                    chunk_id=uuid4(),
                    parent_chunk_id=current_heading_id,
                    element_type="text",
                    content=content,
                    raw_content=None,
                    metadata=metadata,
                    content_hash=h,
                )
            )

            # Advance with overlap: step forward until we've consumed overlap_tokens
            overlap_consumed = 0
            step = 0
            while step < len(acc_toks) and overlap_consumed < len(acc_toks) - overlap_tokens:
                overlap_consumed += len(all_toks[i + step // 1])
                step += 1
            i = max(i + 1, j - max(0, sum(1 for t in all_toks[i:j] if len(t) <= overlap_tokens)))
            # Simpler: restart from j, back-fill overlap
            # Find how many trailing elements cover overlap_tokens
            tail_toks = 0
            tail_start = j
            for k in range(j - 1, i - 1, -1):
                tail_toks += len(all_toks[k])
                if tail_toks >= overlap_tokens:
                    tail_start = k
                    break
            i = tail_start if tail_start < j else j

        buf_elements = []
        buf_tokens = []

    for elem in elements:
        if elem.element_type == "heading":
            flush_text_buffer()
            h = _hash(elem.content, "heading", elem.metadata)
            chunk = Chunk(
                chunk_id=uuid4(),
                parent_chunk_id=None,
                element_type="heading",
                content=elem.content,
                raw_content=elem.raw_content,
                metadata=elem.metadata,
                content_hash=h,
            )
            chunks.append(chunk)
            current_heading_id = chunk.chunk_id

        elif elem.element_type in ("table", "figure"):
            flush_text_buffer()
            h = _hash(elem.content, elem.element_type, elem.metadata)
            content = elem.content
            if elem.element_type == "table":
                summary = _summarize_table(content, h)
                content = f"{summary}\n\n{content}"
            chunk = Chunk(
                chunk_id=uuid4(),
                parent_chunk_id=current_heading_id,
                element_type=elem.element_type,
                content=content,
                raw_content=elem.raw_content,
                metadata=elem.metadata,
                content_hash=h,
            )
            chunks.append(chunk)

        else:  # text
            toks = _encode(elem.content, enc)
            buf_elements.append(elem)
            buf_tokens.append(toks)

    flush_text_buffer()
    return chunks
