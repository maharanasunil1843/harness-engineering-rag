"use client";

import { Component, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { ConstellationHero } from "./ConstellationHero";

/**
 * Hero visual with graceful degradation:
 *   - 3D embedding field is lazy-loaded (ssr:false) so three.js code-splits out
 *     of the main bundle and never blocks first paint.
 *   - The zero-dependency 2D ConstellationHero is the loading placeholder AND
 *     the fallback if WebGL is unavailable or the 3D scene throws.
 */

const EmbeddingField = dynamic(() => import("./EmbeddingField"), {
  ssr: false,
  loading: () => <ConstellationHero />,
});

class WebGLBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return <ConstellationHero />;
    return this.props.children;
  }
}

export function Hero() {
  return (
    <WebGLBoundary>
      <EmbeddingField />
    </WebGLBoundary>
  );
}
