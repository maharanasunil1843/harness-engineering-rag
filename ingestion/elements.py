"""Element schema shared by all parsers and the chunker."""
from typing import Any, Literal

from pydantic import BaseModel, Field

ElementType = Literal["text", "table", "figure", "heading"]


class Element(BaseModel):
    element_type: ElementType
    content: str  # the embeddable text representation
    raw_content: dict[str, Any] | None = None  # structured data (table rows, figure refs)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # metadata keys we use: page, section, parent_heading, bbox, image_path, table_caption


class ParsedDoc(BaseModel):
    title: str
    doc_type: Literal["pdf", "docx", "html"]
    source_path: str
    author: str | None = None
    published: str | None = None  # ISO date or None
    page_count: int | None = None
    elements: list[Element]
