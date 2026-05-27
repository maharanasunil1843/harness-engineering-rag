"""HTML parser using trafilatura for clean content extraction."""
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup

from ingestion.elements import Element, ParsedDoc


def parse_html(path: Path) -> ParsedDoc:
    html = path.read_text(encoding="utf-8")

    # Title
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.text.strip() if title_tag else path.stem

    # Extract clean main content with structure preserved
    extracted = trafilatura.extract(
        html,
        include_tables=True,
        include_links=False,
        include_comments=False,
        output_format="markdown",
        favor_recall=True,
    )
    if not extracted:
        raise ValueError(f"trafilatura failed to extract content from {path}")

    # Split into elements by markdown structure
    elements: list[Element] = []
    section = ""
    for line in extracted.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("# ").strip()
            section = heading_text
            elements.append(
                Element(
                    element_type="heading",
                    content=heading_text,
                    metadata={"level": level, "section": section},
                )
            )
        elif line.startswith("|") and "|" in line[1:]:
            # Markdown table row — accumulate
            # (For MVP: append as text. Production would group rows.)
            elements.append(
                Element(
                    element_type="table",
                    content=line,
                    raw_content={"markdown_row": line},
                    metadata={"section": section},
                )
            )
        else:
            elements.append(
                Element(
                    element_type="text",
                    content=line,
                    metadata={"section": section},
                )
            )

    return ParsedDoc(
        title=title,
        doc_type="html",
        source_path=str(path),
        elements=elements,
    )
