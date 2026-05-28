"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

const features = [
  {
    title: "Hybrid Retrieval",
    description:
      "Dense + BM25 + metadata filter with Reciprocal Rank Fusion. Combines semantic similarity with keyword precision for maximum recall.",
  },
  {
    title: "Text-to-SQL",
    description:
      "Natural language to SQL over the harness catalog with self-correction. Queries structured tables directly when semantic search is insufficient.",
  },
  {
    title: "Semantic Cache",
    description:
      "Embedding-similarity caching via Upstash Redis. Repeat queries return in sub-second latency without hitting the LLM.",
  },
  {
    title: "Per-hop Tracing",
    description:
      "LangSmith integration with trace IDs surfaced per message. Full observability into every retrieval and synthesis step.",
  },
];

const stack = [
  "LangGraph",
  "Claude",
  "pgvector",
  "Supabase",
  "FastAPI",
  "Next.js",
];

export default function LandingPage() {
  const { isSignedIn } = useAuth();

  return (
    <div className="min-h-screen bg-[#0A0A0F] text-zinc-100 flex flex-col">
      <nav className="border-b border-[#1E1E2E] px-6 py-4 flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-400 tracking-wide uppercase">
          Harness Engineering RAG
        </span>
        <div className="flex items-center gap-3">
          {isSignedIn ? (
            <Link
              href="/chat"
              className="text-sm px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 transition-colors"
            >
              Go to Chat
            </Link>
          ) : (
            <>
              <Link
                href="/sign-in"
                className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors"
              >
                Sign in
              </Link>
              <Link
                href="/sign-up"
                className="text-sm px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 transition-colors"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </nav>

      <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-20">
        <div className="mb-16">
          <div className="inline-flex items-center gap-2 text-xs text-zinc-500 border border-[#1E1E2E] rounded-full px-3 py-1 mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            MVP — 420 chunks ingested
          </div>

          <h1 className="text-4xl font-semibold tracking-tight text-zinc-100 mb-4">
            Harness Engineering RAG
          </h1>
          <p className="text-lg text-zinc-400 max-w-2xl leading-relaxed mb-10">
            Agentic retrieval-augmented generation over the harness engineering
            corpus. Hybrid retrieval, text-to-SQL, semantic caching, per-hop
            tracing.
          </p>

          <div className="flex items-center gap-3 flex-wrap">
            <Link
              href={isSignedIn ? "/chat" : "/sign-in"}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-blue-600 hover:bg-blue-500 text-sm font-medium transition-colors"
            >
              {isSignedIn ? "Go to Chat" : "Start Querying"}
              <svg
                className="w-4 h-4"
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
              href="https://github.com/sunil1843/harness-engineering-rag"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-[#1E1E2E] hover:border-zinc-600 text-sm font-medium text-zinc-400 hover:text-zinc-100 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path
                  fillRule="evenodd"
                  clipRule="evenodd"
                  d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                />
              </svg>
              View on GitHub
            </a>
          </div>
        </div>

        <div className="mb-16">
          <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-6">
            Capabilities
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {features.map((f) => (
              <div
                key={f.title}
                className="p-5 rounded-lg border border-[#1E1E2E] bg-[#12121A] hover:border-zinc-700 transition-colors"
              >
                <h3 className="text-sm font-medium text-zinc-100 mb-2">
                  {f.title}
                </h3>
                <p className="text-sm text-zinc-500 leading-relaxed">
                  {f.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-[#1E1E2E] pt-8">
          <p className="text-xs text-zinc-600 mb-3">Stack</p>
          <div className="flex flex-wrap gap-2">
            {stack.map((item) => (
              <span
                key={item}
                className="text-xs text-zinc-400 px-2.5 py-1 rounded border border-[#1E1E2E] bg-[#12121A]"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
