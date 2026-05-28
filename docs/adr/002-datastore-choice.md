# ADR 002: Datastore Choice

**Status:** Accepted
**Date:** 2026-05-28

## Context

Need Postgres with pgvector. Evaluated Supabase and Neon.

## Decision

Supabase for MVP. Neon evaluated as the production migration target for its autoscaling pooler and serverless cold-start profile.

## Consequences

- Supabase dashboard accelerates debugging during rapid development.
- Session pooler connection string used for Lambda compatibility.
- Migration to Neon is a connection string change, not a re-architecture.
