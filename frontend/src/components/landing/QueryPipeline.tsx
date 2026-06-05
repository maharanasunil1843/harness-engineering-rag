"use client";

import { Fragment } from "react";
import { Reveal } from "./Reveal";

/**
 * Animated left-to-right visualization of the LangGraph supervisor flow.
 * Nodes pulse; connectors carry a flowing gradient; a "packet" travels the
 * track — an at-a-glance picture of what the system does per query. All CSS
 * (see globals.css), no dependencies, reduced-motion aware.
 */
const STAGES = [
  { label: "Query", sub: "user question", color: "#3B82F6" },
  { label: "Rewrite", sub: "follow-up + intent", color: "#3B82F6" },
  { label: "Cache", sub: "exact + verify", color: "#22C55E" },
  { label: "Retrieve", sub: "pgvector + SQL", color: "#14B8A6" },
  { label: "Synthesize", sub: "cited · Sonnet", color: "#EA580C" },
  { label: "Stream", sub: "live tokens", color: "#3B82F6" },
];

const EVENTS = ["status", "source", "token", "done"];

export function QueryPipeline() {
  return (
    <section className="mx-auto w-full max-w-5xl px-6 py-20">
      <Reveal>
        <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          How a query flows
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
          Each turn resolves follow-ups against conversation memory, checks the
          verified cache, routes to hybrid retrieval and text-to-SQL, then
          synthesizes a cited answer — streamed token by token over SSE.
        </p>
      </Reveal>

      <Reveal delay={120} className="relative mt-10">
        {/* Traveling packet (md+ only) along the full-width track. */}
        <div className="pointer-events-none absolute inset-x-0 top-1/2 hidden md:block">
          <div className="animate-packet absolute h-2 w-2 -translate-y-1/2 rounded-full bg-blue-400 shadow-[0_0_12px_3px_rgba(96,165,250,0.8)]" />
        </div>

        <div className="relative flex flex-col items-stretch gap-3 md:flex-row md:items-center">
          {STAGES.map((s, i) => (
            <Fragment key={s.label}>
              <div className="relative z-10 flex items-center gap-2.5 rounded-lg border border-[#1E1E2E] bg-[#12121A] px-3.5 py-2.5">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full animate-pulse-glow"
                  style={{
                    backgroundColor: s.color,
                    animationDelay: `${i * 0.3}s`,
                  }}
                />
                <div className="leading-tight">
                  <div className="text-sm font-medium text-zinc-100">
                    {s.label}
                  </div>
                  <div className="text-[11px] text-zinc-500">{s.sub}</div>
                </div>
              </div>

              {i < STAGES.length - 1 && (
                <div className="animate-flow hidden h-px flex-1 bg-gradient-to-r from-[#1E1E2E] via-blue-500 to-[#1E1E2E] md:block" />
              )}
            </Fragment>
          ))}
        </div>
      </Reveal>

      <Reveal delay={220}>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-2 text-[11px]">
          <span className="text-zinc-600">SSE events</span>
          {EVENTS.map((e) => (
            <code
              key={e}
              className="rounded border border-[#1E1E2E] bg-[#12121A] px-2 py-0.5 font-mono text-zinc-400"
            >
              {e}
            </code>
          ))}
        </div>
      </Reveal>
    </section>
  );
}
