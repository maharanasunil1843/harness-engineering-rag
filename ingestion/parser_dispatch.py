"""Routes a file to the right parser by extension."""
from pathlib import Path

from ingestion.elements import ParsedDoc
from ingestion.parsers.docx_parser import parse_docx
from ingestion.parsers.html_parser import parse_html
from ingestion.parsers.pdf_parser import parse_pdf


def parse(path: Path) -> ParsedDoc:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix in {".html", ".htm"}:
        return parse_html(path)
    if suffix == ".docx":
        return parse_docx(path)
    raise ValueError(f"Unsupported file type: {suffix} ({path})")
