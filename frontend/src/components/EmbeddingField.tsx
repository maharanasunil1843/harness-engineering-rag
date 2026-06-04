"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

/**
 * An aurora gradient mesh — a slow, domain-warped flow of color (indigo → blue
 * → cyan) drifting behind the hero copy, in the spirit of the Stripe/Linear
 * backdrops. A single full-screen shader plane: smooth and coherent (never
 * noisy), so text stays legible over it. Cursor subtly warps the flow.
 * Lazy-loaded and isolated (see Hero.tsx); reduced-motion freezes it.
 */

const NOISE_GLSL = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(
      i.z+vec4(0.0,i1.z,i2.z,1.0))
    + i.y+vec4(0.0,i1.y,i2.y,1.0))
    + i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){
  float v=0.0; float a=0.5;
  for(int i=0;i<4;i++){ v+=a*snoise(p); p*=2.0; a*=0.5; }
  return v;
}
`;

const VERT = /* glsl */ `
varying vec2 vUv;
void main(){
  vUv=uv;
  gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
}
`;

const FRAG = /* glsl */ `
precision highp float;
uniform float uTime;
uniform vec2 uMouse;
uniform float uAspect;
varying vec2 vUv;
${NOISE_GLSL}
void main(){
  vec2 p=(vUv*2.0-1.0);
  p.x*=uAspect;
  p+=uMouse*0.18;              // cursor warps the flow
  float t=uTime*0.06;

  // Domain warping → organic aurora ribbons.
  float q1=fbm(vec3(p*1.1,t));
  float q2=fbm(vec3(p*1.1+vec2(5.2,1.3),t));
  vec2 q=vec2(q1,q2);
  float r1=fbm(vec3(p*1.1+0.5*q+vec2(1.7,9.2),t*1.2));
  float r2=fbm(vec3(p*1.1+0.5*q+vec2(8.3,2.8),t*1.2));
  vec2 r=vec2(r1,r2);
  float n=fbm(vec3(p*1.1+0.6*r,t))*0.5+0.5;

  // Cool palette anchored on the theme: near-black → indigo → blue → cyan.
  vec3 c0=vec3(0.039,0.039,0.059);
  vec3 c1=vec3(0.157,0.137,0.486);
  vec3 c2=vec3(0.231,0.510,0.965);
  vec3 c3=vec3(0.133,0.827,0.933);
  vec3 col=mix(c0,c1,smoothstep(0.05,0.45,n));
  col=mix(col,c2,smoothstep(0.40,0.72,n));
  col=mix(col,c3,smoothstep(0.74,0.98,n));

  // Keep it muted so the title reads; fade toward the page bg at the edges.
  col*=0.78;
  float vig=smoothstep(1.45,0.25,length(vUv*2.0-1.0));
  col=mix(c0,col,vig);

  gl_FragColor=vec4(col,1.0);
}
`;

function Aurora({ reduceMotion }: { reduceMotion: boolean }) {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const mouse = useRef(new THREE.Vector2(0, 0));
  const viewport = useThree((s) => s.viewport);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uMouse: { value: new THREE.Vector2(0, 0) },
      uAspect: { value: 1 },
    }),
    [],
  );

  useFrame((state, delta) => {
    const mat = matRef.current;
    const mesh = meshRef.current;
    if (!mat || !mesh) return;
    if (!reduceMotion) mat.uniforms.uTime.value += delta;
    mouse.current.x += (state.pointer.x - mouse.current.x) * 0.05;
    mouse.current.y += (state.pointer.y - mouse.current.y) * 0.05;
    mat.uniforms.uMouse.value.copy(mouse.current);
    // Keep the plane filling the viewport and the aspect correct.
    mesh.scale.set(state.viewport.width, state.viewport.height, 1);
    mat.uniforms.uAspect.value = state.viewport.width / state.viewport.height;
  });

  return (
    <mesh ref={meshRef} scale={[viewport.width, viewport.height, 1]}>
      <planeGeometry args={[1, 1]} />
      <shaderMaterial
        ref={matRef}
        uniforms={uniforms}
        vertexShader={VERT}
        fragmentShader={FRAG}
      />
    </mesh>
  );
}

export default function EmbeddingField() {
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <Canvas
      className="h-full w-full"
      camera={{ position: [0, 0, 3], fov: 60 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
    >
      <Aurora reduceMotion={reduceMotion} />
    </Canvas>
  );
}
