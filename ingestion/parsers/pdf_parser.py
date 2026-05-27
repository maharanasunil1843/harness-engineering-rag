"""PyMuPDF-based PDF parser with table and figure extraction."""
import statistics
from pathlib import Path

import fitz  # PyMuPDF

from ingestion.elements import Element, ParsedDoc

_HEADING_SIZE_MULTIPLIER = 1.15  # must be >= this × median body size
_HEADING_MAX_CHARS = 120
_HEADING_SIZE_P90_PERCENTILE = 0.90  # "top 10%" threshold
_SENTENCE_ENDINGS = {".", "!", "?", ":"}
_MIN_TEXT_CHARS = 20  # drop blocks shorter than this unless heading


def _is_bold(span: dict) -> bool:
    # PyMuPDF span flags: bit 4 (value 16) = bold
    return bool(span.get("flags", 0) & 16)


def _classify_heading(
    text: str,
    max_size: float,
    span_bold: bool,
    median_size: float,
    p90_size: float,
) -> bool:
    """Return True only if ALL five heading criteria are satisfied."""
    if max_size < _HEADING_SIZE_MULTIPLIER * median_size:
        return False
    if len(text) > _HEADING_MAX_CHARS:
        return False
    if text and text[-1] in _SENTENCE_ENDINGS:
        return False
    if not (span_bold or max_size >= p90_size):
        return False
    if not any(c.isalpha() for c in text):
        return False
    return True


def parse_pdf(path: Path) -> ParsedDoc:
    doc = fitz.open(str(path))

    # ── First pass: collect font statistics ──────────────────────────────────
    all_sizes: list[float] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0)
                    if s > 0:
                        all_sizes.append(s)

    if all_sizes:
        median_size = statistics.median(all_sizes)
        sorted_sizes = sorted(all_sizes)
        p90_idx = max(0, int(len(sorted_sizes) * _HEADING_SIZE_P90_PERCENTILE) - 1)
        p90_size = sorted_sizes[p90_idx]
    else:
        median_size = 10.0
        p90_size = 14.0

    title = doc.metadata.get("title", "").strip() or path.stem
    author = doc.metadata.get("author", "").strip() or None
    page_count = doc.page_count

    images_dir = Path("data/images") / path.stem
    images_dir.mkdir(parents=True, exist_ok=True)

    elements: list[Element] = []
    fig_n = 0

    # ── Second pass: extract elements ────────────────────────────────────────
    for page_num, page in enumerate(doc, start=1):
        # --- Tables: find first to mark covered regions ----------------------
        table_finder = page.find_tables()
        table_bboxes: list[fitz.Rect] = []
        for table in table_finder.tables:
            table_rect = fitz.Rect(table.bbox)
            table_bboxes.append(table_rect)
            extracted = table.extract()
            if not extracted:
                continue
            headers = [str(c) if c else "" for c in extracted[0]]
            rows = [[str(c) if c else "" for c in row] for row in extracted[1:]]
            md_rows = (
                ["| " + " | ".join(headers) + " |",
                 "| " + " | ".join("---" for _ in headers) + " |"]
                + ["| " + " | ".join(row) + " |" for row in rows]
            )
            elements.append(
                Element(
                    element_type="table",
                    content="\n".join(md_rows),
                    raw_content={"rows": rows, "headers": headers},
                    metadata={
                        "page": page_num,
                        "bbox": [table_rect.x0, table_rect.y0, table_rect.x1, table_rect.y1],
                    },
                )
            )

        # --- Text blocks in reading order ------------------------------------
        blocks = page.get_text("dict", sort=True)["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            block_rect = fitz.Rect(block["bbox"])
            if any(block_rect.intersects(tb) for tb in table_bboxes):
                continue

            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = " ".join(s["text"] for s in spans).strip()
                if not text:
                    continue

                max_size = max((s.get("size", 0) for s in spans), default=0)
                span_bold = any(_is_bold(s) for s in spans)
                bbox = line["bbox"]

                is_heading = _classify_heading(
                    text, max_size, span_bold, median_size, p90_size
                )

                # Apply length filter: drop short non-heading blocks
                if not is_heading and len(text) < _MIN_TEXT_CHARS:
                    continue

                elements.append(
                    Element(
                        element_type="heading" if is_heading else "text",
                        content=text,
                        metadata={"page": page_num, "bbox": list(bbox)},
                    )
                )

        # --- Figures ---------------------------------------------------------
        img_list = page.get_images(full=True)
        for img_info in img_list:
            xref = img_info[0]
            fig_n += 1
            img_path = images_dir / f"figure_{fig_n}.png"
            try:
                base_img = doc.extract_image(xref)
                img_path.write_bytes(base_img["image"])
            except Exception:
                pass

            img_rect = page.get_image_rects(xref)
            caption = ""
            if img_rect:
                ir = img_rect[0]
                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    br = fitz.Rect(block["bbox"])
                    if br.y0 >= ir.y1 and br.y0 <= ir.y1 + 100:
                        candidate = " ".join(
                            span["text"]
                            for ln in block.get("lines", [])
                            for span in ln.get("spans", [])
                        ).strip()
                        if candidate:
                            caption = candidate
                            break

            elements.append(
                Element(
                    element_type="figure",
                    content=caption or f"Figure {fig_n}",
                    raw_content={"image_path": str(img_path), "page": page_num},
                    metadata={
                        "page": page_num,
                        "bbox": list(ir) if img_rect else [],
                    },
                )
            )

    doc.close()
    return ParsedDoc(
        title=title,
        doc_type="pdf",
        source_path=str(path),
        author=author,
        page_count=page_count,
        elements=elements,
    )
