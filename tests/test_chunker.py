"""Verify chunker invariants: headings solo, tables/figures intact, hash deterministic."""
from unittest.mock import patch

from ingestion.chunker import _hash, chunk_elements
from ingestion.elements import Element


def _text(content: str, **meta) -> Element:
    return Element(element_type="text", content=content, metadata=meta)


def _heading(content: str, **meta) -> Element:
    return Element(element_type="heading", content=content, metadata=meta)


def _table(content: str, raw=None, **meta) -> Element:
    return Element(element_type="table", content=content, raw_content=raw, metadata=meta)


def _figure(content: str, raw=None, **meta) -> Element:
    return Element(element_type="figure", content=content, raw_content=raw, metadata=meta)


def test_heading_emits_single_chunk():
    chunks = chunk_elements([_heading("Introduction")])
    assert len(chunks) == 1
    assert chunks[0].element_type == "heading"
    assert chunks[0].content == "Introduction"


def test_table_never_split():
    # A table whose text length far exceeds the target token count must still
    # be emitted as one chunk — splitting tables would destroy structure.
    big = " ".join(["cell"] * 4000)
    with patch("ingestion.chunker._summarize_table", return_value="table summary"):
        chunks = chunk_elements([_table(big)], target_tokens=128)
    tables = [c for c in chunks if c.element_type == "table"]
    assert len(tables) == 1
    # Table content includes the prepended summary.
    assert "cell cell" in tables[0].content


def test_figure_never_split():
    big = " ".join(["pixel"] * 2000)
    chunks = chunk_elements([_figure(big, raw={"path": "x.png"})], target_tokens=64)
    figures = [c for c in chunks if c.element_type == "figure"]
    assert len(figures) == 1
    assert figures[0].raw_content == {"path": "x.png"}


def test_long_text_split_at_token_boundary():
    # The chunker packs multiple text elements until target_tokens is reached.
    # Feed many small elements so the buffer is split into several chunks.
    elements = [_text(" ".join([f"word{j}" for j in range(40)])) for _ in range(30)]
    chunks = chunk_elements(elements, target_tokens=128, overlap_tokens=16)
    text_chunks = [c for c in chunks if c.element_type == "text"]
    assert len(text_chunks) >= 2


def test_content_hash_is_deterministic():
    h1 = _hash("hello world", "text", {"page": 1, "source": "a.pdf"})
    h2 = _hash("hello world", "text", {"source": "a.pdf", "page": 1})
    h3 = _hash("hello world", "text", {"page": 1, "source": "a.pdf"})
    assert h1 == h2  # metadata key order doesn't matter
    assert h1 == h3


def test_content_hash_differs_on_content_change():
    h1 = _hash("hello", "text", {})
    h2 = _hash("world", "text", {})
    assert h1 != h2


def test_content_hash_differs_on_element_type_change():
    h1 = _hash("hello", "text", {})
    h2 = _hash("hello", "heading", {})
    assert h1 != h2


def test_heading_then_text_links_parent():
    chunks = chunk_elements(
        [_heading("Section A"), _text("body content")],
        target_tokens=128,
    )
    heading = next(c for c in chunks if c.element_type == "heading")
    texts = [c for c in chunks if c.element_type == "text"]
    assert texts
    for t in texts:
        assert t.parent_chunk_id == heading.chunk_id
