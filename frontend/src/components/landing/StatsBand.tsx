"use client";

import { useEffect, useRef, useState } from "react";
import { Reveal } from "./Reveal";

/**
 * Verified metrics (counted against the live DB) that animate up on scroll.
 * See README "At a glance" — these are real row counts, not marketing.
 */
const STATS: { value: number; label: string; suffix?: string }[] = [
  { value: 420, label: "Vector chunks" },
  { value: 108, label: "Catalog components" },
  { value: 43, label: "Failure modes" },
  { value: 14, label: "Harnesses" },
  { value: 7, label: "Source documents" },
  { value: 9, label: "Benchmarks" },
];

function CountUp({ to, duration = 1300 }: { to: number; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [val, setVal] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        obs.disconnect();

        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          setVal(to);
          return;
        }
        const start = performance.now();
        let raf = 0;
        const tick = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
          setVal(Math.round(eased * to));
          if (t < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
        cleanup = () => cancelAnimationFrame(raf);
      },
      { threshold: 0.4 },
    );
    let cleanup = () => {};
    obs.observe(el);
    return () => {
      obs.disconnect();
      cleanup();
    };
  }, [to, duration]);

  return <span ref={ref}>{val}</span>;
}

export function StatsBand() {
  return (
    <section className="border-y border-[#1E1E2E] bg-[#0c0c12]">
      <div className="mx-auto grid max-w-5xl grid-cols-2 gap-px px-6 py-14 sm:grid-cols-3 md:grid-cols-6">
        {STATS.map((s, i) => (
          <Reveal key={s.label} delay={i * 70} className="text-center">
            <div className="bg-gradient-to-b from-white to-zinc-500 bg-clip-text text-4xl font-semibold tracking-tight text-transparent tabular-nums">
              <CountUp to={s.value} />
              {s.suffix}
            </div>
            <div className="mt-1.5 text-xs uppercase tracking-wider text-zinc-500">
              {s.label}
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
