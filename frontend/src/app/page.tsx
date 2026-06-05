"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { Hero } from "@/components/Hero";
import { StatsBand } from "@/components/landing/StatsBand";
import { QueryPipeline } from "@/components/landing/QueryPipeline";
import { SampleQueries } from "@/components/landing/SampleQueries";
import { CorpusFooter } from "@/components/landing/CorpusFooter";

const features = [
  {
    title: "Conversational Memory",
    description:
      "Server-side multi-turn memory with a rolling summary. Follow-ups like “what about its failure modes?” are resolved into standalone queries before retrieval.",
  },
  {
    title: "Hybrid Retrieval",
    description:
      "Dense + sparse with Reciprocal Rank Fusion and parent-chunk expansion. Combines semantic similarity with keyword precision for maximum recall.",
  },
  {
    title: "Text-to-SQL",
    description:
      "Natural language to SQL over the harness catalog with self-correction. Queries structured tables directly when semantic search is insufficient.",
  },
  {
    title: "Verified Semantic Cache",
    description:
      "Exact + semantic lookup on Redis before any LLM call. Gray-zone matches pass a cheap LLM check, so vague rephrasings hit without serving a wrong answer.",
  },
  {
    title: "Real-time Streaming",
    description:
      "Answers stream token-by-token from the model over SSE, on a fully async event loop. No simulated typing — genuine live synthesis.",
  },
  {
    title: "Per-hop Tracing",
    description:
      "LangSmith integration with trace IDs surfaced per message. Observability into every retrieval and synthesis step.",
  },
];

const pills = [
  "LangGraph supervisor",
  "Conversational memory",
  "Hybrid retrieval",
  "Text-to-SQL",
  "Verified cache",
  "Token streaming",
];

const stack = ["LangGraph", "Claude", "pgvector", "Supabase", "FastAPI", "Next.js"];

const GITHUB_URL = "https://github.com/maharanasunil1843/harness-engineering-rag";

export default function LandingPage() {
  const { isSignedIn } = useAuth();

  return (
    <div className="min-h-screen bg-[#0A0A0F] text-zinc-100">
      {/* Top nav — floats over the hero. */}
      <nav className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-6 py-4">
        <span className="text-sm font-medium uppercase tracking-wide text-zinc-400">
          Harness Engineering RAG
        </span>
        <div className="flex items-center gap-3">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-zinc-400 transition-colors hover:text-zinc-100"
          >
            GitHub
          </a>
          {isSignedIn ? (
            <Link
              href="/chat"
              className="rounded bg-blue-600 px-3 py-1.5 text-sm transition-colors hover:bg-blue-500"
            >
              Go to Chat
            </Link>
          ) : (
            <>
              <Link
                href="/sign-in"
                className="text-sm text-zinc-400 transition-colors hover:text-zinc-100"
              >
                Sign in
              </Link>
              <Link
                href="/sign-up"
                className="rounded bg-blue-600 px-3 py-1.5 text-sm transition-colors hover:bg-blue-500"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* ── Hero: 3D embedding field (lazy) behind centered copy ── */}
      <section className="relative flex h-screen items-center justify-center overflow-hidden">
        <div className="absolute inset-0">
          <Hero />
        </div>
        {/* Vignette darkens the edges over the flow field. */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,_transparent_0%,_#0A0A0F_75%)]" />
        {/* Soft scrim: a contrast pad directly behind the hero copy. */}
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-[440px] w-[720px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#0A0A0F]/70 blur-3xl" />

        <div className="relative z-10 mx-auto max-w-3xl px-6 text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[#1E1E2E] bg-[#0A0A0F]/60 px-3 py-1 text-xs text-zinc-500 backdrop-blur">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
            MVP — 420 chunks ingested · move your cursor
          </div>

          <h1 className="bg-gradient-to-b from-white to-zinc-500 bg-clip-text text-5xl font-semibold tracking-tight text-transparent drop-shadow-[0_2px_24px_rgba(0,0,0,0.55)] sm:text-6xl">
            Harness Engineering RAG
          </h1>

          <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-zinc-300 [text-shadow:_0_1px_12px_rgba(0,0,0,0.7)] sm:text-lg">
            A multi-turn agentic supervisor resolves follow-ups, then routes
            through hybrid retrieval, text-to-SQL, and a verified cache — and
            streams a cited answer token by token.
          </p>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
            {pills.map((p) => (
              <span
                key={p}
                className="rounded-full border border-[#1E1E2E] bg-[#12121A]/70 px-3 py-1 text-xs text-zinc-400 backdrop-blur"
              >
                {p}
              </span>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={isSignedIn ? "/chat" : "/sign-in"}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-5 py-2.5 text-sm font-medium transition-colors hover:bg-blue-500"
            >
              {isSignedIn ? "Go to Chat" : "Try it live"}
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M13 7l5 5m0 0l-5 5m5-5H6"
                />
              </svg>
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-md border border-[#1E1E2E] bg-[#0A0A0F]/40 px-5 py-2.5 text-sm font-medium text-zinc-400 backdrop-blur transition-colors hover:border-zinc-600 hover:text-zinc-100"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                <path
                  fillRule="evenodd"
                  clipRule="evenodd"
                  d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                />
              </svg>
              View on GitHub
            </a>
          </div>

          <div className="mt-14 flex justify-center">
            <span className="animate-bounce text-zinc-600" aria-hidden="true">
              ↓
            </span>
          </div>
        </div>
      </section>

      {/* ── Verified metrics ── */}
      <StatsBand />

      {/* ── Animated query pipeline ── */}
      <QueryPipeline />

      {/* ── Capabilities ── */}
      <section className="mx-auto w-full max-w-4xl px-6 py-20">
        <h2 className="mb-6 text-xs font-medium uppercase tracking-wider text-zinc-500">
          Capabilities
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-lg border border-[#1E1E2E] bg-[#12121A] p-5 transition-colors hover:border-zinc-700"
            >
              <h3 className="mb-2 text-sm font-medium text-zinc-100">{f.title}</h3>
              <p className="text-sm leading-relaxed text-zinc-500">
                {f.description}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-12 border-t border-[#1E1E2E] pt-8">
          <p className="mb-3 text-xs text-zinc-600">Stack</p>
          <div className="flex flex-wrap gap-2">
            {stack.map((item) => (
              <span
                key={item}
                className="rounded border border-[#1E1E2E] bg-[#12121A] px-2.5 py-1 text-xs text-zinc-400"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── Sample queries ── */}
      <SampleQueries />

      {/* ── Corpus + footer ── */}
      <CorpusFooter />
    </div>
  );
}
