# Harness Engineering RAG

Agentic retrieval-augmented generation over the harness engineering corpus — hybrid retrieval, text-to-SQL, semantic caching, and per-hop tracing in a production-grade architecture.

## What this is

A natural-language interface over a curated corpus of harness engineering literature (Trivedy, Osmani, Anthropic Labs, HumanLayer, Red Hat) plus a practitioner case study mapping these principles to a production enterprise RAG system. The system routes queries through a LangGraph supervisor to specialized workers — hybrid retrieval over pgvector, text-to-SQL over a structured catalog, or both in parallel — then synthesizes cited answers with confidence scoring.

Built as a portfolio MVP demonstrating the full production architecture at reduced scale. Every architectural decision is documented in `docs/adr/`.

## Key metrics

| Metric | Value |
|---|---|
| Corpus | 7 documents across 3 formats (PDF, HTML, DOCX) |
| Chunks in pgvector | 420 |
| Structured catalog | 108 components · 43 failure modes · 14 harnesses · 7 practitioners · 9 benchmarks |
| Retrieval | Hybrid dense + BM25 with reciprocal rank fusion, parent-chunk expansion |
| Cache | Semantic similarity (cosine threshold 0.92) — sub-1.2s on hit vs ~28s cold |
| Routing | 7/7 correct on integration test (retrieval, SQL, hybrid, direct, cross-doc, DOCX, cache) |
| Cost per query | ~₹1.5 blended (Haiku workers + Sonnet synthesis + prompt caching) |

## Architecture

```text
User → Next.js + Clerk Auth → FastAPI (SSE Streaming)
                                   │
                         LangGraph Supervisor
                         ├── Query Rewriter + Intent Classifier (Sonnet)
                         ├── Semantic Cache Check (Redis)
                         ├── Rate Limiter (Redis sliding window)
                         │
                         ▼ routes to:
             ┌───────────┼───────────────┐
        Hybrid Retrieval  Text-to-SQL    Direct Answer
        (pgvector + BM25)  (self-correcting, Haiku)
             └───────────┼───────────────┘
                         │
                   Synthesizer (Sonnet — cited answer + confidence)
                         │
                   Cache Set → Response (SSE stream)

Observability: LangSmith per-hop tracing · Prompt caching · Token tracking
```

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph with conditional routing) |
| Models | Claude Opus 4.7 (planner), Sonnet 4.6 (synthesizer), Haiku 4.5 (workers) |
| Embeddings | OpenAI text-embedding-3-small (1536-dim) |
| Vector store | Supabase Postgres + pgvector (HNSW index) |
| Sparse retrieval | Postgres tsvector + ts_rank_cd |
| Structured data | 6 catalog tables for text-to-SQL agent |
| Cache | Upstash Redis (semantic similarity + sliding-window rate limiter) |
| Backend | FastAPI (async, SSE streaming, Mangum for Lambda) |
| Frontend | Next.js 16, Tailwind v4, Clerk auth |
| Observability | LangSmith per-hop tracing, OpenTelemetry GenAI conventions |
| CI | GitHub Actions with RAGAS eval gates |
| IaC | Terraform modules for AWS Lambda + API Gateway (see `infra/`) |
| Package management | uv with lockfile |

## Corpus

| # | Document | Format | Author |
|---|---|---|---|
| 1 | Agent Harness Engineering | PDF | Addy Osmani |
| 2 | Self-Improving Coding Agents | PDF | Addy Osmani |
| 3 | Harness Design for Long-Running Development | PDF | Anthropic (Prithvi Rajasekaran) |
| 4 | Skill Issue: Harness Engineering for Coding Agents | PDF | HumanLayer (Kyle) |
| 5 | The Anatomy of an Agent Harness | PDF | Viv Trivedy |
| 6 | Structured Workflows for AI-Assisted Development | HTML | Red Hat Developer |
| 7 | Harness Engineering Applied to Production Enterprise RAG | DOCX | Sunil Maharana |

## Dual-extraction ingestion

The ingestion pipeline reads each document once and produces two outputs:

1. **Chunks → pgvector** — section-aware chunking (512 tokens, 64 overlap), tables and figures kept atomic. Format-specific parsers: PyMuPDF (PDF), trafilatura (HTML), python-docx (DOCX).
2. **Entities → SQL catalog** — LLM-driven extraction (Haiku 4.5) populates `harness_components`, `failure_modes`, `practitioners`, `harnesses`, `benchmark_results`. Every row carries `source_doc_id` provenance.

Parser selection: Docling and unstructured evaluated and rejected — their PyTorch/layout-model dependencies (~4 GB) weren't justified for this born-digital corpus. See `docs/adr/001-parser-selection.md`.

## Demo queries

| Query | Path | What it demonstrates |
|---|---|---|
| "What is a harness?" | Retrieval | Core definition with source citations |
| "List all components in the safety category" | SQL | Text-to-SQL over the catalog |
| "What failure modes do hooks address?" | Hybrid | Retrieval + SQL fused |
| "How does Red Hat's workflow relate to Anthropic's planner/evaluator?" | Cross-doc | Synthesis across articles |
| "How are harness principles applied in manufacturing?" | DOCX retrieval | Surfaces the practitioner case study |
| Repeat any query | Cache hit | Sub-1.2s semantic cache |

## Quickstart

```bash
git clone https://github.com/maharanasunil1843/harness-engineering-rag.git
cd harness-engineering-rag

# Backend
cp .env.example .env   # fill in API keys
uv sync
make ingest
make smoke
uv run uvicorn app.api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
cp .env.local.example .env.local   # fill in Clerk keys
npm install && npm run dev

# Open http://localhost:3000
```

## Live deployment (Vercel + Railway)

Frontend on Vercel, backend on Railway, data layer unchanged (Supabase + Upstash).
Both platforms auto-deploy on push to `main` via their GitHub integrations — there
is no GitHub Actions deploy job. See `docs/adr/004-railway-over-lambda.md` for why
Railway (a long-lived container) rather than the documented Lambda path: API
Gateway buffers responses and cannot stream SSE, which the chat depends on.

**Deploy order matters** — stand up the backend first so its URL is available for
the frontend's `NEXT_PUBLIC_API_URL`.

1. **Backend → Railway.** New Project → Deploy from GitHub repo. Railway builds the
   root `Dockerfile` (config in `railway.json`, healthcheck `/api/health`). Set
   these variables (values come from your `.env`):

   | Variable | Source |
   |---|---|
   | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | model providers |
   | `DATABASE_URL` | Supabase session pooler connection string |
   | `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Supabase project |
   | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis |
   | `LANGSMITH_API_KEY` | LangSmith (or set `LANGSMITH_TRACING=false`) |
   | `ADMIN_KEY` | optional; gates `/api/metrics` |

2. **Frontend → Vercel.** Import the repo, set **Root Directory** to `frontend`,
   and add:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | the Railway URL, e.g. `https://<app>.up.railway.app` |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | Clerk |
   | `NEXT_PUBLIC_SHOW_TRACES` | optional; `true` to surface LangSmith links |

CORS already allows `*.vercel.app` (`app/api/middleware.py`); add a custom domain
to that regex if you use one. The browser streams SSE directly from Railway, so
Vercel's serverless response limits do not apply.

## Evaluation

```bash
make eval        # full 20-query RAGAS eval
make eval-quick  # first 5 queries only
```

CI blocks merge if RAGAS faithfulness drops below 0.85. See `.github/workflows/eval.yml`.

## Project structure

```
├── app/
│   ├── agents/         # LangGraph supervisor, query rewriter, synthesizer
│   ├── retrieval/      # Hybrid retrieval, semantic cache, rate limiter
│   ├── sql/            # Text-to-SQL agent with self-correction
│   ├── observability/  # LangSmith tracing, token tracking
│   └── api/            # FastAPI routes, SSE streaming, Lambda handler
├── ingestion/          # Parser dispatcher, chunker, embedder, entity extractor
├── evals/              # RAGAS golden set and evaluation harness
├── frontend/           # Next.js 16 + Clerk + Tailwind v4
├── infra/terraform/    # AWS Lambda + API Gateway IaC
├── scripts/            # Smoke test, integration tests, DB utilities
├── docs/adr/           # Architecture decision records
├── Dockerfile          # Backend container for Railway (uv, deterministic)
├── railway.json        # Railway build/deploy config (Dockerfile + healthcheck)
├── CLAUDE.md           # Agent harness configuration for this repo
└── Makefile
```

## Architecture decisions

| ADR | Decision |
|---|---|
| 001 | Format-specific parsers over Docling/unstructured |
| 002 | Supabase for MVP, Neon for production serverless |
| 003 | Heading classifier ratchet, entity quality validation |
| 004 | Railway over Lambda for the MVP backend (SSE streaming) |

## AWS production migration path

| MVP (current) | Production AWS |
|---|---|
| Supabase (pgvector) | RDS Postgres + Pinecone |
| Upstash Redis | ElastiCache |
| Vercel (frontend) | CloudFront + S3 |
| Railway (backend) | Lambda + API Gateway |
| Clerk | Cognito |

Lambda handler (Mangum) and Terraform modules are included. Migration is a configuration change, not a re-architecture.

## License

MIT
