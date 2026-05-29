# ADR 004: Railway over AWS Lambda for the MVP Backend

**Status:** Accepted
**Date:** 2026-05-29

## Context

The CLAUDE.md stack pins "FastAPI backend ... Mangum for Lambda packaging," and
`app/api/lambda_handler.py` plus `infra/terraform/` target AWS Lambda + API
Gateway. That path is sound for the documented production migration, but the MVP
needs a live, shareable demo for interviews, deployed quickly.

The product's core feature is a streaming chat: the frontend consumes a
Server-Sent Events stream from `POST /api/query/stream` (status → source →
token → done). AWS Lambda behind API Gateway (REST or HTTP API) buffers the full
response and does not support incremental SSE — the browser would receive
nothing until the entire pipeline completed, re-breaking the exact streaming UX
that the chat depends on. Lambda response streaming exists only via Function
URLs with adapters that Mangum does not implement.

## Options evaluated

1. **AWS Lambda + API Gateway (Mangum)** — Matches the documented production
   path, but no SSE streaming; cold starts add latency to an LLM pipeline that
   is already multi-second.
2. **Railway (container)** — Long-lived uvicorn process, native HTTP streaming,
   GitHub-integrated auto-deploy, env-var management in-dashboard. Deterministic
   Docker build from the committed `uv.lock`.
3. **Vercel serverless functions for the backend** — Same streaming/timeout
   constraints as Lambda for long LLM calls; keeps everything on one platform
   but does not fit a long-running agentic pipeline.

## Decision

Deploy the MVP backend to Railway as a long-lived container; deploy the Next.js
frontend to Vercel. Supabase (pgvector) and Upstash (Redis) remain the data
layer unchanged. The Lambda handler and Terraform modules are retained for the
documented production migration path — this is an MVP hosting choice, not a
removal of the AWS target.

## Consequences

- SSE streaming works end to end in the live demo; no API Gateway buffering.
- No cold starts on the request path; the container stays warm.
- Auto-deploy on push to `main` via Railway's GitHub integration; the redundant
  GitHub Actions deploy job is removed (see commit removing `deploy.yml`).
- A second hosting target now exists alongside the AWS path. The production
  migration in the README is unchanged: moving to Lambda remains a packaging
  change (Mangum handler already present), gated on solving SSE there or
  switching that surface to non-streaming.
- CORS already permits `*.vercel.app`, so the deployed frontend origin is
  accepted without code changes.
