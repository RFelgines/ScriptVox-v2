"use client";

// Candidat "Plasma" -- démonstrateur de l'écart avec ElevenLabs/ChatGPT :
// fragment shader WebGL brut (zéro dépendance), bruit fbm domain-warped
// calculé PAR PIXEL et nourri par un temps continu (jamais périodique,
// la matière se déforme au lieu de translater), silhouette du disque
// elle-même déformée par le bruit. Seed par voix (décale le domaine du
// bruit : deux voix n'affichent jamais la même matière). Énergie pilotée
// par playing + var(--voice-amp) ; au repos le temps est GELÉ (plus de
// rAF une fois la transition retombée -- zéro coût, même règle que la
// prod). Un contexte WebGL par instance : si ce candidat est retenu, il
// sera réservé aux orbes "héros" (player, page Voix, segment actif) avec
// repli CSS pour les dizaines d'orbes statiques de la transcription
// (plafond navigateur ~8-16 contextes simultanés, cf. Phase 22).

import { useEffect, useRef } from "react";

const VERT = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform vec2 u_res;
uniform float u_time;
uniform float u_seed;
uniform float u_energy;
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_c3;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 345.45));
  p += dot(p, p + 34.345);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 4; i++) {
    v += a * noise(p);
    p = p * 2.03 + 11.7;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * u_res) / (0.5 * u_res.y);
  float t = u_time * 0.28;
  float r = length(uv);

  // Silhouette : rayon déformé par un bruit échantillonné SUR le cercle
  // (continu, pas de couture d'angle) -- amplitude liée à l'énergie.
  vec2 circ = uv / max(r, 1e-4);
  float edgeN = fbm(circ * 1.6 + u_seed + vec2(t * 0.55, -t * 0.4)) - 0.5;
  float radius = 0.80 + edgeN * (0.035 + 0.11 * u_energy);
  float mask = smoothstep(radius, radius - 0.035, r);
  if (mask <= 0.0) { gl_FragColor = vec4(0.0); return; }

  // Matière : fbm dont le domaine est déformé par un autre fbm (domain
  // warping) -- c'est ce qui donne les volutes fluides.
  vec2 q = uv * 1.35 + vec2(u_seed * 1.7, u_seed);
  vec2 w = vec2(
    fbm(q + vec2(t * 0.9, t * 0.6)),
    fbm(q + vec2(5.2 - t * 0.7, 1.3 + t * 0.5))
  );
  float n = fbm(q + (1.6 + 0.9 * u_energy) * w + vec2(t * 0.4, -t * 0.3));

  vec3 col = mix(u_c1, u_c2, smoothstep(0.2, 0.78, n));
  col = mix(col, u_c3, smoothstep(0.55, 0.95, fbm(q * 1.8 - w * 1.2 - vec2(t * 0.5, t * 0.35))));
  // Profondeur tonale : veines sombres là où le bruit est bas.
  col *= 0.62 + 0.75 * n;

  // Cœur lumineux modulé par le bruit et l'énergie (respire avec la voix) --
  // teinté vers la couleur de la voix pour ne pas délaver l'identité.
  float core = smoothstep(0.85, 0.0, r) * (0.08 + 0.45 * u_energy);
  col += mix(u_c2, vec3(1.0), 0.55) * core * (0.55 + 0.45 * fbm(q * 2.6 + w + vec2(t * 1.6, t * 1.2)));

  // Modelé sphérique : assombrissement du bord + lumière zénithale douce.
  col *= 1.0 - 0.5 * smoothstep(0.45, 1.0, r / max(radius, 1e-4));
  col += vec3(1.0) * 0.10 * smoothstep(0.75, 0.0, length(uv - vec2(-0.38, 0.46)));

  // Repos : désaturé + assombri (même distinction d'état que la prod).
  float g = dot(col, vec3(0.299, 0.587, 0.114));
  col = mix(vec3(g), col, 0.55 + 0.45 * u_energy) * (0.78 + 0.30 * u_energy);

  gl_FragColor = vec4(col * mask, mask);
}
`;

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)];
}

function readAmp(): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--voice-amp"));
  return Number.isFinite(v) ? v : 0.55;
}

type GlState = {
  gl: WebGLRenderingContext;
  uniforms: Record<string, WebGLUniformLocation | null>;
  time: number;
  energy: number;
};

export default function ShaderOrb({ hue, playing, size, seed }: { hue: number; playing: boolean; size: number; seed?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<GlState | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: true });
    if (!gl) return;

    const compile = (type: number, src: string) => {
      const sh = gl.createShader(type)!;
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      return sh;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const u = (name: string) => gl.getUniformLocation(prog, name);
    stateRef.current = {
      gl,
      uniforms: { res: u("u_res"), time: u("u_time"), seed: u("u_seed"), energy: u("u_energy"), c1: u("u_c1"), c2: u("u_c2"), c3: u("u_c3") },
      time: 0,
      energy: 0,
    };
    gl.uniform2f(stateRef.current.uniforms.res, canvas.width, canvas.height);
    gl.viewport(0, 0, canvas.width, canvas.height);
    return () => {
      stateRef.current = null;
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, []);

  // Couleurs + seed (recalculés à chaque changement de teinte, frame redessinée).
  useEffect(() => {
    const st = stateRef.current;
    if (!st) return;
    const { gl, uniforms } = st;
    gl.uniform3f(uniforms.c1, ...hslToRgb(hue, 0.8, 0.42));
    gl.uniform3f(uniforms.c2, ...hslToRgb((hue + 30) % 360, 0.95, 0.6));
    gl.uniform3f(uniforms.c3, ...hslToRgb((hue + 322) % 360, 0.85, 0.55));
    gl.uniform1f(uniforms.seed, (((seed ?? hue) % 360) / 360) * 43.7 + 7.3);
    gl.uniform1f(uniforms.time, st.time);
    gl.uniform1f(uniforms.energy, st.energy);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }, [hue, seed]);

  // Boucle d'animation : tourne pendant la lecture + le temps que la
  // transition d'énergie retombe, puis s'arrête (temps gelé, zéro coût).
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const st = stateRef.current;
      if (!st) return;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const target = playing ? 0.35 + 0.65 * readAmp() : 0;
      st.energy += (target - st.energy) * Math.min(1, dt * 6);
      if (playing) st.time += dt * (0.45 + 0.75 * st.energy);
      const { gl, uniforms } = st;
      gl.uniform1f(uniforms.time, st.time);
      gl.uniform1f(uniforms.energy, st.energy);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (playing || Math.abs(st.energy - target) > 0.004) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const dpr = 2;
  return (
    <canvas
      ref={canvasRef}
      width={size * dpr}
      height={size * dpr}
      style={{ width: size, height: size, display: "block" }}
      aria-hidden="true"
    />
  );
}
