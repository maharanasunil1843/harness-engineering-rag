# CLAUDE.md

Configuration for Claude Code working in this repository. Treated as the project's agent harness configuration in the sense described by the corpus this project is built on — a curated rulebook that earns every line against a real constraint, not a brainstorm.

Keep this file under 80 lines. Every rule below traces to a specific decision or failure mode.

## Project context

Agentic RAG MVP over the harness engineering corpus (Trivedy, Osmani, Anthropic Labs, HumanLayer, Red Hat). Reference architecture mirrors the author's production system at Sugna Metals Ltd. — agentic supervisor pattern, polyglot data layer, per-hop tracing, CI eval gates.

## Stack (do not deviate without an ADR)

- Python 3.11 managed by `uv`. Lockfile (`uv.lock`) is committed.
- Postgres + pgvector via Supabase (session pooler for connections).
- Redis via Upstash for semantic cache and rate limiting.
- LangGraph + langgraph-supervisor for orchestration.
- Claude routing: Opus 4.7 (planner), Sonnet 4.6 (synthesizer), Haiku 4.5 (workers).
- OpenAI text-embedding-3-small for embeddings (1536-dim).
- FastAPI backend, Next.js frontend, Mangum for Lambda packaging.
- Observability via LangSmith + OpenTelemetry GenAI conventions.

## Parsing decisions

- PDFs → PyMuPDF. HTML → trafilatura. DOCX → python-docx.
- Docling and `unstructured` evaluated and rejected: their PyTorch/layout-model dependencies (~4 GB) are not justified for this born-digital corpus. See `docs/adr/001-parser-selection.md`.

## Workflow boundary between human and Claude Code

| Delegated to Claude Code | Human-authored |
| --- | --- |
| Scaffolding, boilerplate, file creation | Architecture, data modeling, prompt design |
| Format-specific parser implementations | Agentic supervisor logic and routing |
| Test cases against documented contracts | ADRs and harness design decisions |
| Refactors with clearly stated invariants | Trade-off reviews, dependency justification |

## Hard rules

- Never read, print, or modify `.env`, `.env.*`, or any file containing secrets. Enforced via `.claude/settings.local.json`.
- Never add a Python dependency without a one-line justification in the commit message tracing it to a documented need (the ratchet principle from the corpus).
- Never commit on my behalf. Surface diffs for review.
- Never bypass the `data/raw/` ingestion path with hard-coded test corpora.
- Tables in chunks must round-trip through markdown — preserve `raw_content` as structured JSON in metadata.

## Quality gates

- `ruff check .` must pass before commit.
- `pytest` must pass before any merge to main.
- RAGAS faithfulness on the golden set must stay above 0.85; gate enforced in CI.

## Style

- No emojis in code or commit messages.
- Commit messages use Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`).
- Type hints on every public function. Pydantic models for any boundary between modules.
- Each ADR in `docs/adr/` follows the format: Context, Decision, Consequences, Status.
