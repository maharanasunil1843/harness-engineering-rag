"use client";

import { Reveal } from "./Reveal";

/**
 * The demo-query set from the README, each tagged with the route the supervisor
 * takes. Hover lifts the card. Shows breadth of routing without a live call.
 */
const PATH_COLORS: Record<string, string> = {
  Retrieval: "text-blue-300 border-blue-500/30 bg-blue-500/10",
  SQL: "text-teal-300 border-teal-500/30 bg-teal-500/10",
  Hybrid: "text-purple-300 border-purple-500/30 bg-purple-500/10",
  "Follow-up": "text-indigo-300 border-indigo-500/30 bg-indigo-500/10",
  DOCX: "text-zinc-300 border-zinc-500/30 bg-zinc-500/10",
  Cache: "text-green-300 border-green-500/30 bg-green-500/10",
};

const QUERIES: { q: string; path: keyof typeof PATH_COLORS; note: string }[] = [
  { q: "What is a harness?", path: "Retrieval", note: "Core definition with source citations" },
  { q: "List all components in the safety category", path: "SQL", note: "Text-to-SQL over the catalog" },
  { q: "What failure modes do hooks address?", path: "Hybrid", note: "Retrieval + SQL fused" },
  { q: "…then: What are its main components?", path: "Follow-up", note: "Conversation memory resolves “its”" },
  { q: "Can you explain what a harness is for AI agents?", path: "Cache", note: "Vague rephrase hits via the verifier" },
  { q: "How are harness principles applied in manufacturing?", path: "DOCX", note: "Surfaces the practitioner case study" },
];

export function SampleQueries() {
  return (
    <section className="mx-auto w-full max-w-4xl px-6 py-20">
      <Reveal>
        <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Ask it anything
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
          The supervisor picks the right tool per question — retrieval,
          text-to-SQL, both, or a cache hit.
        </p>
      </Reveal>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {QUERIES.map((item, i) => (
          <Reveal key={item.q} delay={i * 60}>
            <div className="group h-full rounded-lg border border-[#1E1E2E] bg-[#12121A] p-5 transition-all hover:-translate-y-0.5 hover:border-zinc-700">
              <div className="mb-3 flex items-start justify-between gap-3">
                <p className="text-sm font-medium leading-snug text-zinc-100">
                  &ldquo;{item.q}&rdquo;
                </p>
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${PATH_COLORS[item.path]}`}
                >
                  {item.path}
                </span>
              </div>
              <p className="text-xs leading-relaxed text-zinc-500">{item.note}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
