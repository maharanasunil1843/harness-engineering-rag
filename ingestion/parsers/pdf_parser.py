"""PyMuPDF-based PDF parser with table and figure extraction."""
from pathlib import Path

import fitz  # PyMuPDF

from ingestion.elements import Element, ParsedDoc


def parse_pdf(path: Path) -> ParsedDoc:
    doc = fitz.open(str(path))

    # Collect all font sizes to determine heading threshold (top 20%)
    all_sizes: list[float] = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    all_sizes.append(span["size"])

    all_sizes.sort()
    heading_threshold = (
        all_sizes[int(len(all_sizes) * 0.80)] if all_sizes else 14.0
    )

    title = doc.metadata.get("title", "").strip() or path.stem
    author = doc.metadata.get("author", "").strip() or None
    page_count = doc.page_count

    images_dir = Path("data/images") / path.stem
    images_dir.mkdir(parents=True, exist_ok=True)

    elements: list[Element] = []
    fig_n = 0

    for page_num, page in enumerate(doc, start=1):
        # --- Tables (find before text to mark covered regions) ---
        table_finder = page.find_tables()
        table_bboxes: list[fitz.Rect] = []
        for table in table_finder.tables:
            # table.bbox may be a fitz.Rect or a plain tuple depending on PyMuPDF version
            table_rect = fitz.Rect(table.bbox)
            table_bboxes.append(table_rect)
            extracted = table.extract()
            if not extracted:
                continue
            headers = [str(c) if c else "" for c in extracted[0]]
            rows = [[str(c) if c else "" for c in row] for row in extracted[1:]]
            md_rows = [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
            ] + ["| " + " | ".join(row) + " |" for row in rows]
            md = "\n".join(md_rows)
            elements.append(
                Element(
                    element_type="table",
                    content=md,
                    raw_content={"rows": rows, "headers": headers},
                    metadata={
                        "page": page_num,
                        "bbox": [table_rect.x0, table_rect.y0, table_rect.x1, table_rect.y1],
                    },
                )
            )

        # --- Text blocks in reading order ---
        blocks = page.get_text("dict", sort=True)["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            block_rect = fitz.Rect(block["bbox"])
            # Skip if this block is inside a table region
            if any(block_rect.intersects(tb) for tb in table_bboxes):
                continue

            for line in block.get("lines", []):
                text = " ".join(
                    span["text"] for span in line.get("spans", [])
                ).strip()
                if len(text) < 10:
                    continue

                max_size = max(
                    (span["size"] for span in line.get("spans", [])), default=0
                )
                bbox = line["bbox"]
                etype = "heading" if max_size >= heading_threshold else "text"
                elements.append(
                    Element(
                        element_type=etype,
                        content=text,
                        metadata={
                            "page": page_num,
                            "bbox": list(bbox),
                        },
                    )
                )

        # --- Figures ---
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

            # Look for a caption: nearest text block below the image rect
            img_rect = page.get_image_rects(xref)
            caption = ""
            if img_rect:
                ir = img_rect[0]
                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    br = fitz.Rect(block["bbox"])
                    # Within 100pt below the image
                    if br.y0 >= ir.y1 and br.y0 <= ir.y1 + 100:
                        candidate = " ".join(
                            span["text"]
                            for line in block.get("lines", [])
                            for span in line.get("spans", [])
                        ).strip()
                        if candidate:
                            caption = candidate
                            break

            elements.append(
                Element(
                    element_type="figure",
                    content=caption or f"Figure {fig_n}",
                    raw_content={
                        "image_path": str(img_path),
                        "page": page_num,
                    },
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
