"""python-docx parser preserving paragraph/table interleave order."""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ingestion.elements import Element, ParsedDoc


def _table_to_markdown(table: Table) -> tuple[str, list[list[str]], list[str]]:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not rows:
        return "", [], []
    headers = rows[0]
    data_rows = rows[1:]
    md_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ] + ["| " + " | ".join(r) + " |" for r in data_rows]
    return "\n".join(md_lines), data_rows, headers


def parse_docx(path: Path) -> ParsedDoc:
    doc = Document(str(path))

    title = ""
    try:
        title = (doc.core_properties.title or "").strip()
    except Exception:
        pass
    if not title:
        title = path.stem

    author: str | None = None
    try:
        author = (doc.core_properties.author or "").strip() or None
    except Exception:
        pass

    elements: list[Element] = []
    current_section = ""

    # Iterate body children to preserve paragraph/table interleave
    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style_name = para.style.name if para.style else ""
            is_heading = style_name.lower().startswith("heading")
            if is_heading:
                current_section = text
                elements.append(
                    Element(
                        element_type="heading",
                        content=text,
                        metadata={
                            "section": current_section,
                            "style": style_name,
                        },
                    )
                )
            else:
                elements.append(
                    Element(
                        element_type="text",
                        content=text,
                        metadata={
                            "section": current_section,
                            "style": style_name,
                        },
                    )
                )

        elif tag == "tbl":
            # Reconstruct a Table object from the element
            tbl_element = child
            # Find the parent body element to pass to Table constructor
            table = Table(tbl_element, doc)
            md, data_rows, headers = _table_to_markdown(table)
            if md:
                elements.append(
                    Element(
                        element_type="table",
                        content=md,
                        raw_content={"rows": data_rows, "headers": headers},
                        metadata={"section": current_section},
                    )
                )

        elif tag == "sdt":
            # Structured document tags — extract text from nested paragraphs
            for p_elem in child.findall(".//" + qn("w:p")):
                para = Paragraph(p_elem, doc)
                text = para.text.strip()
                if text:
                    elements.append(
                        Element(
                            element_type="text",
                            content=text,
                            metadata={"section": current_section, "style": "sdt"},
                        )
                    )

    return ParsedDoc(
        title=title,
        doc_type="docx",
        source_path=str(path),
        author=author,
        elements=elements,
    )
