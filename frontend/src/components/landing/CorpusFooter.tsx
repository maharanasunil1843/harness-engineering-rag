"use client";

import { Reveal } from "./Reveal";

const GITHUB_URL = "https://github.com/maharanasunil1843/harness-engineering-rag";
const API_HEALTH =
  "https://harness-engineering-rag-production.up.railway.app/api/health";

const FORMAT_COLORS: Record<string, string> = {
  PDF: "text-red-300 border-red-500/30",
  HTML: "text-amber-300 border-amber-500/30",
  DOCX: "text-blue-300 border-blue-500/30",
};

const CORPUS: { title: string; format: keyof typeof FORMAT_COLORS; author: string }[] = [
  { title: "Agent Harness Engineering", format: "PDF", author: "Addy Osmani" },
  { title: "Self-Improving Coding Agents", format: "PDF", author: "Addy Osmani" },
  { title: "Harness Design for Long-Running Development", format: "PDF", author: "Anthropic" },
  { title: "Skill Issue: Harness Engineering for Coding Agents", format: "PDF", author: "HumanLayer" },
  { title: "The Anatomy of an Agent Harness", format: "PDF", author: "Viv Trivedy" },
  { title: "Structured Workflows for AI-Assisted Development", format: "HTML", author: "Red Hat Developer" },
  { title: "Harness Engineering Applied to Production Enterprise RAG", format: "DOCX", author: "Sunil Maharana" },
];

const STACK = ["LangGraph", "Claude", "pgvector", "Supabase", "Upstash", "FastAPI", "Next.js"];

export function CorpusFooter() {
  return (
    <>
      <section className="mx-auto w-full max-w-4xl px-6 py-20">
        <Reveal>
          <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            The knowledge base
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
            Seven documents across three formats — practitioner literature plus a
            production case study — dual-extracted into vectors and a structured
            catalog.
          </p>
        </Reveal>

        <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CORPUS.map((doc, i) => (
            <Reveal key={doc.title} delay={i * 50}>
              <div className="flex h-full items-start gap-3 rounded-lg border border-[#1E1E2E] bg-[#12121A] p-4 transition-colors hover:border-zinc-700">
                <span
                  className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium ${FORMAT_COLORS[doc.format]}`}
                >
                  {doc.format}
                </span>
                <div className="leading-snug">
                  <p className="text-sm font-medium text-zinc-200">{doc.title}</p>
                  <p className="mt-0.5 text-xs text-zinc-500">{doc.author}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <footer className="border-t border-[#1E1E2E] bg-[#0c0c12]">
        <div className="mx-auto max-w-5xl px-6 py-12">
          <div className="flex flex-col gap-8 md:flex-row md:items-start md:justify-between">
            <div className="max-w-sm">
              <p className="text-sm font-medium uppercase tracking-wide text-zinc-300">
                Harness Engineering RAG
              </p>
              <p className="mt-2 text-xs leading-relaxed text-zinc-500">
                Agentic RAG over the harness-engineering corpus. Hybrid retrieval,
                text-to-SQL, semantic caching, per-hop tracing.
              </p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {STACK.map((s) => (
                  <span
                    key={s}
                    className="rounded border border-[#1E1E2E] px-2 py-0.5 text-[11px] text-zinc-500"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2 text-sm">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 transition-colors hover:text-zinc-100"
              >
                GitHub →
              </a>
              <a
                href={API_HEALTH}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 transition-colors hover:text-zinc-100"
              >
                API health →
              </a>
            </div>
          </div>

          <p className="mt-10 text-xs text-zinc-600">
            Built by Sunil Maharana · MIT License
          </p>
        </div>
      </footer>
    </>
  );
}
