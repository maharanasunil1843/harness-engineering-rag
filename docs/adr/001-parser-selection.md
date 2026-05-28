# ADR 001: Parser Selection

**Status:** Accepted
**Date:** 2026-05-28

## Context

The corpus consists of 7 born-digital documents across 3 formats (PDF, HTML, DOCX).

## Options evaluated

1. **Docling** (IBM) — Unified parser, layout-aware. Requires PyTorch + layout models (~4 GB).
2. **Unstructured** — Similar unified approach. PDF support requires detectron2/PyTorch (~4 GB).
3. **Format-specific parsers** — PyMuPDF (PDF), trafilatura (HTML), python-docx (DOCX). Total ~20 MB.

## Decision

Format-specific parsers. The born-digital corpus has no scanned pages requiring OCR. The 200x dependency reduction is justified against zero documented extraction failures.

## Consequences

- Fast install, small container image, no GPU dependency.
- If corpus expands to scanned documents, revisit Docling.
- Follows the harness-engineering ratchet principle: add complexity only against a real failure.
