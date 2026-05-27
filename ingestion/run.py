"""End-to-end ingestion. Usage: uv run python -m ingestion.run [--dir data/raw]"""
import argparse
from pathlib import Path

from dotenv import load_dotenv

from ingestion.chunker import chunk_elements
from ingestion.db import upsert_chunks, upsert_document
from ingestion.embedder import embed_chunks
from ingestion.entity_extractor import extract_entities, upsert_entities
from ingestion.parser_dispatch import parse


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/raw")
    ap.add_argument(
        "--skip-entities",
        action="store_true",
        help="Skip entity extraction (chunks only)",
    )
    args = ap.parse_args()

    files = sorted(Path(args.dir).iterdir())
    files = [f for f in files if f.suffix.lower() in {".pdf", ".html", ".htm", ".docx"}]

    print(f"Found {len(files)} documents.")
    for i, f in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {f.name}")
        parsed = parse(f)
        print(
            f"  Parsed: {len(parsed.elements)} elements "
            f"({sum(1 for e in parsed.elements if e.element_type == 'text')} text, "
            f"{sum(1 for e in parsed.elements if e.element_type == 'table')} table, "
            f"{sum(1 for e in parsed.elements if e.element_type == 'figure')} figure, "
            f"{sum(1 for e in parsed.elements if e.element_type == 'heading')} heading)"
        )

        doc_id = upsert_document(parsed)
        chunks = chunk_elements(parsed.elements)
        print(f"  Chunks: {len(chunks)}")

        chunks = embed_chunks(chunks)
        upsert_chunks(doc_id, chunks)
        print("  Loaded chunks to pgvector.")

        if not args.skip_entities:
            result = extract_entities(doc_id, parsed)
            upsert_entities(result)
            print(
                f"  Entities: {len(result.components)} components, "
                f"{len(result.failures)} failures, "
                f"{len(result.practitioners)} practitioners"
            )

    print("\n✅ Ingestion complete.")


if __name__ == "__main__":
    main()
