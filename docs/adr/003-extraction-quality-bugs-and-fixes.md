# ADR 003: Extraction Quality Ratchet

**Status:** Accepted
**Date:** 2026-05-28

## Context

Initial ingestion produced 1,849 chunks and 166 harness components. The PDF heading classifier was over-firing (247 headings, 11 text blocks in one document).

## Root cause

PyMuPDF font-size distribution is narrow in these PDFs. The top-20% heuristic classified nearly every line as a heading.

## Fix

Five-rule conjunction: font size >= 1.15x median, text <= 120 chars, no sentence-terminal punctuation, bold OR top-10% size, contains alphabetic chars.

## Result

420 chunks, 108 components (validated clean). Entity extraction prompt tightened with name-length and specificity rules.

## Consequence

Added validation query: longest entity names must be real patterns, not heading fragments. The bug generated the validation check — the ratchet in practice.
