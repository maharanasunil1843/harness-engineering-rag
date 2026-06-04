"use client";

import { useEffect, useRef } from "react";

/**
 * A mouse-reactive "neural constellation" rendered on a Canvas2D surface.
 *
 * Particles drift slowly and link to nearby neighbours; the cursor acts as a
 * gravity well that nudges particles and brightens the links around it — an
 * abstract nod to embeddings clustering in vector space. Pure Canvas2D, no
 * dependencies. Honours `prefers-reduced-motion` (renders a single static
 * frame) and scales to the device pixel ratio for crisp lines.
 */

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  hue: number; // index into PALETTE
}

// Theme-matched node colours: accent blue, data-layer teal, LLM orange.
const PALETTE = ["#3B82F6", "#14B8A6", "#EA580C"];

const LINK_DISTANCE = 130; // px: draw a link when two particles are closer
const MOUSE_RADIUS = 180; // px: cursor influence radius
const DENSITY = 14000; // one particle per N css-pixels of area
const MAX_PARTICLES = 140;

export function ConstellationHero() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    let width = 0;
    let height = 0;
    let dpr = 1;
    let particles: Particle[] = [];
    // Mouse lives off-screen until the pointer actually enters the canvas.
    const mouse = { x: -9999, y: -9999, active: false };
    let raf = 0;

    function seed() {
      const count = Math.min(
        MAX_PARTICLES,
        Math.floor((width * height) / DENSITY),
      );
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.6 + 0.8,
        hue: Math.floor(Math.random() * PALETTE.length),
      }));
    }

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas!.width = Math.floor(width * dpr);
      canvas!.height = Math.floor(height * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function draw() {
      ctx!.clearRect(0, 0, width, height);

      for (const p of particles) {
        // Drift.
        p.x += p.vx;
        p.y += p.vy;

        // Wrap around the edges so the field never empties out.
        if (p.x < -20) p.x = width + 20;
        if (p.x > width + 20) p.x = -20;
        if (p.y < -20) p.y = height + 20;
        if (p.y > height + 20) p.y = -20;

        // Cursor gravity well: gently push particles outward from the pointer.
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.hypot(dx, dy);
          if (dist < MOUSE_RADIUS && dist > 0.01) {
            const force = (1 - dist / MOUSE_RADIUS) * 0.6;
            p.x += (dx / dist) * force;
            p.y += (dy / dist) * force;
          }
        }
      }

      // Links — O(n^2) but n is small (<=140), so this stays cheap.
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.hypot(dx, dy);
          if (dist > LINK_DISTANCE) continue;

          let alpha = (1 - dist / LINK_DISTANCE) * 0.4;
          // Brighten links whose midpoint sits near the cursor.
          if (mouse.active) {
            const mx = (a.x + b.x) / 2 - mouse.x;
            const my = (a.y + b.y) / 2 - mouse.y;
            const md = Math.hypot(mx, my);
            if (md < MOUSE_RADIUS) alpha += (1 - md / MOUSE_RADIUS) * 0.5;
          }

          ctx!.strokeStyle = `rgba(96, 165, 250, ${Math.min(alpha, 0.9)})`;
          ctx!.lineWidth = 0.6;
          ctx!.beginPath();
          ctx!.moveTo(a.x, a.y);
          ctx!.lineTo(b.x, b.y);
          ctx!.stroke();
        }
      }

      // Nodes on top of the links.
      for (const p of particles) {
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = PALETTE[p.hue];
        ctx!.globalAlpha = 0.9;
        ctx!.fill();
        ctx!.globalAlpha = 1;
      }

      if (!reduceMotion) raf = requestAnimationFrame(draw);
    }

    function onMove(e: PointerEvent) {
      const rect = canvas!.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.active = true;
    }
    function onLeave() {
      mouse.active = false;
      mouse.x = -9999;
      mouse.y = -9999;
    }

    resize();
    draw(); // one frame guaranteed even under reduced-motion

    window.addEventListener("resize", resize);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="absolute inset-0 h-full w-full"
    />
  );
}
