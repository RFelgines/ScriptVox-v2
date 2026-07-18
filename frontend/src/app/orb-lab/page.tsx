"use client";

// Page temporaire de brainstorm visuel. Correction : la précédente
// "recréation" de l'original était fausse (structure radial-gradient statique
// au lieu du conic-gradient tournant). Voici la vraie version d'origine
// (capture fournie par l'utilisateur pour vérification), + 4 variantes de
// "nuages qui se dispersent" en remplacement de "dérive large" (l'utilisateur
// a validé le principe : dégradés radiaux doux animés en transform+opacity
// uniquement -- pas de filter:blur, compositor-only donc peu coûteux même
// avec beaucoup d'instances simultanées). "Lumière zénithale" et "duo
// chromatique" supprimés. Aurora Ribbon inchangé. À supprimer une fois une
// direction choisie -- voir mémoire "voice-orb-redesign-elevenlabs".
// Itération 2 (2026-07-18) : carte "Orbe vivante (prod)" = composant réel de
// production, + 5 candidats (Comète / Nébuleuse / Sonar / Lave / Couronne)
// à trancher -- même règle figé/actif que la prod.
import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import VoiceOrb from "@/components/VoiceOrb";

const SIZE = 160;

const HUE_ORANGE = 20;
const HUE_BLUE = 200;
const HUE_PINK = 320;
const HUE_GREEN = 140;
const HUE_PURPLE = 260;
const SWATCH_HUES = [HUE_ORANGE, HUE_BLUE, HUE_PINK, HUE_GREEN, HUE_PURPLE];

const KEYFRAMES = `
/* --- Glass Bubble original (fidèle à la capture) --- */
@keyframes orbSpinSlow { to { transform: rotate(360deg); } }
@keyframes orbGlassBreathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.045); } }

/* --- Nuages qui se dispersent : transform + opacity uniquement (compositor-
   only, pas de repaint) -- performant même avec beaucoup d'instances. --- */
@keyframes cloudPulse {
  0% { transform: translate(-22%, -10%) scale(0.9); opacity: 0.15; }
  25% { transform: translate(6%, -8%) scale(1.05); opacity: 0.9; }
  50% { transform: translate(20%, 8%) scale(1); opacity: 0.85; }
  75% { transform: translate(-2%, 14%) scale(0.95); opacity: 0.45; }
  100% { transform: translate(-22%, -10%) scale(0.9); opacity: 0.15; }
}
@keyframes cloudBloomA { 0% { transform: scale(0.5); opacity: 0.08; } 50% { transform: scale(1.2); opacity: 0.95; } 100% { transform: scale(0.5); opacity: 0.08; } }

/* --- Aurora Ribbon (inchangé) --- */
@keyframes orbDrift1 { 0%,100% { transform: translate(-10%, -6%) rotate(0deg); } 50% { transform: translate(8%, 4%) rotate(8deg); } }
@keyframes orbDrift2 { 0%,100% { transform: translate(8%, 8%) rotate(0deg); } 50% { transform: translate(-6%, -8%) rotate(-10deg); } }
@keyframes orbTwinkle { 0%,100% { opacity: 0.15; } 50% { opacity: 0.85; } }
@keyframes arFlickerContainer { 0%,100% { filter: brightness(1); } 25% { filter: brightness(1.25); } 50% { filter: brightness(0.95); } 75% { filter: brightness(1.4); } }
@keyframes arWaveSwell { 0%,100% { transform: scale(1); } 50% { transform: scale(1.09); } }
@keyframes arSparkle { 0%,100% { opacity: 0.25; transform: scale(0.7); } 50% { opacity: 1; transform: scale(1.8); } }
@keyframes arWindRipple1 { 0%,100% { transform: translate(-10%,-6%) rotate(0deg); } 50% { transform: translate(10%,6%) rotate(6deg); } }
@keyframes arWindRipple2 { 0%,100% { transform: translate(8%,8%) rotate(0deg); } 50% { transform: translate(-10%,-8%) rotate(-6deg); } }
@keyframes arVortexWrap { to { transform: rotate(360deg); } }

/* --- Candidats itération 2 (2026-07-18) : même règle que la prod --
   figé = animation-play-state paused (jamais animation:none), actif = tout
   s'anime. transform + opacity uniquement. --- */
@keyframes lorbSpin { to { transform: rotate(360deg); } }
@keyframes lorbCometHead { 0%,100% { opacity: .7; transform: scale(.9); } 50% { opacity: 1; transform: scale(1.25); } }
@keyframes lorbNebulaA { 0%,100% { transform: translate(-16%,-8%) rotate(0deg) scale(1); } 50% { transform: translate(14%,10%) rotate(14deg) scale(1.15); } }
@keyframes lorbNebulaB { 0%,100% { transform: translate(14%,8%) rotate(0deg) scale(1.05); } 50% { transform: translate(-12%,-12%) rotate(-16deg) scale(.9); } }
@keyframes lorbSonarRing { 0% { transform: scale(.18); opacity: 0; } 12% { opacity: .6; } 100% { transform: scale(1.02); opacity: 0; } }
@keyframes lorbSonarCore { 0%,100% { opacity: .5; transform: scale(.9); } 30% { opacity: .95; transform: scale(1.12); } 60% { opacity: .65; transform: scale(1); } }
@keyframes lorbLavaRise { 0% { transform: translateY(58%) scale(.9,.75); opacity: 0; } 18% { opacity: .85; } 50% { transform: translateY(0%) scale(1.08,1.18); opacity: .9; } 82% { opacity: .6; } 100% { transform: translateY(-58%) scale(.85,.8); opacity: 0; } }
@keyframes lorbCoronaFlare { 0%,100% { opacity: .55; transform: scale(.97); } 18% { opacity: .95; transform: scale(1.01); } 42% { opacity: .65; } 65% { opacity: 1; transform: scale(1.03); } 85% { opacity: .7; } }
`;

function PlayButton({ playing, onClick }: { playing: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={playing ? "Mettre en pause" : "Lire l'animation"}
      className="absolute inset-0 z-10 m-auto flex h-9 w-9 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur-sm transition hover:bg-black/55"
    >
      {playing ? (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <rect x="4" y="3" width="4" height="14" rx="1" />
          <rect x="12" y="3" width="4" height="14" rx="1" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" fill="currentColor" className="ml-0.5 h-4 w-4">
          <path d="M6 3.5l11 6.5-11 6.5V3.5z" />
        </svg>
      )}
    </button>
  );
}

function Swatches({ value, onChange }: { value: number; onChange: (h: number) => void }) {
  return (
    <div className="flex gap-2">
      {SWATCH_HUES.map((h) => (
        <button
          key={h}
          onClick={() => onChange(h)}
          aria-label={`Teinte ${h}`}
          className="h-5 w-5 rounded-full"
          style={{
            background: `hsl(${h} 80% 55%)`,
            boxShadow: value === h ? "0 0 0 2px var(--color-background), 0 0 0 3.5px white" : "none",
          }}
        />
      ))}
    </div>
  );
}

function DesignCard({
  title,
  desc,
  initialHue,
  render,
}: {
  title: string;
  desc: string;
  initialHue: number;
  render: (hue: number, playing: boolean) => ReactNode;
}) {
  const [hue, setHue] = useState(initialHue);
  const [playing, setPlaying] = useState(false);

  return (
    <div className="flex flex-col items-center gap-3 rounded-card border border-border bg-surface p-6">
      <div style={{ width: SIZE, height: SIZE }} className="relative flex shrink-0 items-center justify-center">
        {render(hue, playing)}
        <PlayButton playing={playing} onClick={() => setPlaying(!playing)} />
      </div>
      <div className="max-w-[220px] text-center">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted">{desc}</p>
      </div>
      <Swatches value={hue} onChange={setHue} />
    </div>
  );
}

// Glass Bubble -- ORIGINAL, fidèle à la capture fournie : conic-gradient qui
// tourne (vite en lecture, lentement au repos) + verre en overlay (backdrop-
// blur + bord + ombres internes), reflet déjà retiré précédemment.
function GlassBubbleOriginal({ hue, playing }: { hue: number; playing: boolean }) {
  return (
    <div
      className="relative overflow-hidden rounded-full"
      style={{ width: SIZE, height: SIZE, animation: playing ? "orbGlassBreathe 1s ease-in-out infinite" : "none" }}
    >
      <div
        className="absolute -inset-4"
        style={{
          background: `conic-gradient(from 120deg, hsl(${hue} 85% 62%), hsl(${(hue + 70) % 360} 80% 58%), hsl(${(hue + 200) % 360} 75% 50%), hsl(${hue} 85% 62%))`,
          filter: "blur(14px)",
          animation: `orbSpinSlow ${playing ? 2.2 : 16}s linear infinite`,
        }}
      />
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: "linear-gradient(150deg, rgba(255,255,255,0.5), rgba(255,255,255,0.04) 40%, rgba(255,255,255,0.2) 100%)",
          backdropFilter: "blur(4px) saturate(1.3)",
          border: "1px solid rgba(255,255,255,0.4)",
          boxShadow: "inset 0 10px 16px rgba(255,255,255,0.45), inset 0 -16px 22px rgba(0,0,0,0.2), inset 6px 0 10px rgba(255,255,255,0.08)",
        }}
      />
    </div>
  );
}

// Nuages qui se dispersent -- reprend l'esprit de "dérive large" (une
// couleur qui parcourt la sphère) mais avec de vraies tâches de nuage
// (dégradés radiaux à bords doux, sans filter:blur) qui se cèdent la place :
// l'une s'estompe pendant que l'autre grossit/arrive. Seuls transform et
// opacity sont animés (compositor-only, aucun repaint) -- pensé pour rester
// léger même avec 50+ instances simultanées (cf. transcription).
type CloudConfig = {
  count: number;
  hueStep: number;
  cloudSize: number; // % de la taille du conteneur
  keyframe: string;
  idleDur: number;
  activeDur: number;
};

const CLOUD_TWO: CloudConfig = { count: 2, hueStep: 130, cloudSize: 85, keyframe: "cloudPulse", idleDur: 12, activeDur: 4 };
const CLOUD_THREE: CloudConfig = { count: 3, hueStep: 90, cloudSize: 75, keyframe: "cloudPulse", idleDur: 15, activeDur: 5 };
const CLOUD_BLOOM: CloudConfig = { count: 3, hueStep: 110, cloudSize: 80, keyframe: "cloudBloomA", idleDur: 10, activeDur: 3.2 };
const CLOUD_CURRENT: CloudConfig = { count: 4, hueStep: 70, cloudSize: 65, keyframe: "cloudPulse", idleDur: 18, activeDur: 6 };

function CloudDisperse({ hue, playing, config }: { hue: number; playing: boolean; config: CloudConfig }) {
  const dur = playing ? config.activeDur : config.idleDur;
  return (
    <div className="relative overflow-hidden rounded-full" style={{ width: SIZE, height: SIZE, background: "#101014" }}>
      {Array.from({ length: config.count }, (_, i) => {
        const cloudHue = (hue + i * config.hueStep) % 360;
        const delay = -((i / config.count) * dur);
        return (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              width: `${config.cloudSize}%`,
              height: `${config.cloudSize}%`,
              left: `${(100 - config.cloudSize) / 2}%`,
              top: `${(100 - config.cloudSize) / 2}%`,
              background: `radial-gradient(circle, hsl(${cloudHue} 88% 62%) 0%, hsl(${cloudHue} 88% 62% / 0) 70%)`,
              animation: `${config.keyframe} ${dur}s ease-in-out ${delay}s infinite`,
              willChange: "transform, opacity",
            }}
          />
        );
      })}
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: "linear-gradient(150deg, rgba(255,255,255,0.5), rgba(255,255,255,0.04) 40%, rgba(255,255,255,0.2) 100%)",
          backdropFilter: "saturate(1.3)",
          border: "1px solid rgba(255,255,255,0.4)",
          boxShadow: "inset 0 10px 16px rgba(255,255,255,0.45), inset 0 -16px 22px rgba(0,0,0,0.2), inset 6px 0 10px rgba(255,255,255,0.08)",
        }}
      />
    </div>
  );
}

// Aurora Ribbon -- INCHANGÉ. 5 animations actives : orange=rubans rapides +
// scintillement, bleu=vague ample et lente, rose=étoiles qui explosent en
// éclats, vert=ondulation façon vent, violet=le ciel entier tourbillonne.
function AuroraRibbon({ hue, playing }: { hue: number; playing: boolean }) {
  const driftNames = playing && hue === HUE_GREEN ? ["arWindRipple1", "arWindRipple2"] : ["orbDrift1", "orbDrift2"];
  const speedFactor = playing ? (hue === HUE_BLUE ? 1 : 3.5) : 1;

  const ribbon = (rotate: number, huePart: number, animIndex: 0 | 1, dur: number, opacity: number): CSSProperties => ({
    position: "absolute",
    inset: "-30%",
    background: `linear-gradient(${rotate}deg, transparent, hsl(${huePart} 90% 58% / ${playing && hue !== HUE_BLUE ? opacity * 1.6 : opacity}), transparent)`,
    filter: "blur(9px)",
    mixBlendMode: "screen",
    animation: `${driftNames[animIndex]} ${dur / speedFactor}s ease-in-out infinite`,
  });

  const stars = [
    { x: 22, y: 30, d: 0 },
    { x: 70, y: 20, d: 0.6 },
    { x: 55, y: 65, d: 1.2 },
    { x: 30, y: 80, d: 1.8 },
    { x: 82, y: 55, d: 0.9 },
  ];
  const sparkleExtra = playing && hue === HUE_PINK ? [{ x: 45, y: 45, d: 0.3 }, { x: 62, y: 35, d: 0.9 }] : [];

  const containerAnim =
    playing && hue === HUE_ORANGE
      ? "arFlickerContainer 0.4s ease-in-out infinite"
      : playing && hue === HUE_BLUE
        ? "arWaveSwell 2.8s ease-in-out infinite"
        : "none";

  const inner = (
    <>
      {[...stars, ...sparkleExtra].map((s, i) => (
        <div
          key={i}
          className="absolute rounded-full bg-white"
          style={{
            width: 2,
            height: 2,
            left: `${s.x}%`,
            top: `${s.y}%`,
            animation:
              playing && hue === HUE_PINK
                ? `arSparkle ${0.5 + i * 0.15}s ease-in-out ${s.d}s infinite`
                : `orbTwinkle ${(playing ? 0.6 : 2) + i * (playing ? 0.1 : 0.4)}s ease-in-out ${s.d}s infinite`,
          }}
        />
      ))}
      <div style={ribbon(15, hue, 0, 10, 0.42)} />
      <div style={ribbon(95, (hue + 100) % 360, 1, 12, 0.32)} />
      <div style={ribbon(150, (hue + 210) % 360, 0, 14, 0.28)} />
      <div style={ribbon(60, (hue + 280) % 360, 1, 9, 0.25)} />
    </>
  );

  return (
    <div
      className="relative overflow-hidden rounded-full"
      style={{
        width: SIZE,
        height: SIZE,
        background: `radial-gradient(circle at 50% 40%, hsl(${hue} 45% 12%), #05060a 75%)`,
        animation: containerAnim,
      }}
    >
      {playing && hue === HUE_PURPLE ? (
        <div className="absolute inset-0" style={{ animation: "arVortexWrap 3s linear infinite" }}>
          {inner}
        </div>
      ) : (
        inner
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Candidats itération 2 (2026-07-18) : coquille commune (finition sphérique +
// terne/figé au repos, comme la prod) ; chaque variante ne fournit que ses
// couches internes.
function CandidateShell({ playing, background, children }: { playing: boolean; background: string; children: ReactNode }) {
  return (
    <div
      className="relative overflow-hidden rounded-full"
      style={{
        width: SIZE,
        height: SIZE,
        background,
        filter: playing ? "saturate(1.1) brightness(1.05)" : "saturate(0.8) brightness(0.9)",
        transition: "filter 500ms ease",
      }}
    >
      {children}
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: "linear-gradient(160deg, rgba(255,255,255,0.28), rgba(255,255,255,0.02) 42%, rgba(255,255,255,0.08) 100%)",
          boxShadow: "inset 0 10px 14px rgba(255,255,255,0.35), inset 0 -16px 22px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(255,255,255,0.15)",
        }}
      />
    </div>
  );
}

// Comète : un arc de lumière orbite sur le bord (traîne conique masquée en
// anneau + tête brillante), une étincelle contre-orbite, cœur qui pulse.
function CometOrb({ hue, playing }: { hue: number; playing: boolean }) {
  const ps = playing ? "running" : "paused";
  const ringMask = "radial-gradient(closest-side, transparent 58%, black 66%, black 90%, transparent 96%)";
  return (
    <CandidateShell playing={playing} background={`radial-gradient(circle at 40% 35%, hsl(${hue} 60% 26%), hsl(${hue} 65% 12%) 70%)`}>
      <div
        className="absolute rounded-full"
        style={{
          inset: "18%",
          background: `radial-gradient(closest-side, hsl(${hue} 90% 70% / 0.55), transparent 70%)`,
          animation: "lorbCometHead 2.3s ease-in-out infinite",
          animationPlayState: ps,
        }}
      />
      <div className="absolute" style={{ inset: "4%", animation: "lorbSpin 1.9s linear -0.4s infinite", animationPlayState: ps }}>
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: `conic-gradient(from 0deg, hsl(${hue} 95% 70% / 0) 0deg, hsl(${hue} 95% 70% / 0.9) 80deg, hsl(${(hue + 40) % 360} 95% 75%) 100deg, transparent 130deg)`,
            WebkitMask: ringMask,
            mask: ringMask,
          }}
        />
        <div
          className="absolute rounded-full"
          style={{
            width: "20%",
            height: "20%",
            left: "78%",
            top: "47%",
            background: `radial-gradient(closest-side, white, hsl(${hue} 100% 80%) 40%, transparent 70%)`,
            animation: "lorbCometHead 0.9s ease-in-out infinite",
            animationPlayState: ps,
          }}
        />
      </div>
      <div
        className="absolute"
        style={{ inset: "14%", animation: "lorbSpin 3.1s linear reverse infinite", animationPlayState: ps }}
      >
        <div
          className="absolute rounded-full"
          style={{
            width: "10%",
            height: "10%",
            left: "45%",
            top: "0%",
            background: `radial-gradient(closest-side, hsl(${(hue + 40) % 360} 100% 85%), transparent 70%)`,
          }}
        />
      </div>
    </CandidateShell>
  );
}

// Nébuleuse bichrome : deux nuages complémentaires (teinte de la voix +
// contre-couleur pleine) qui tourbillonnent en sens opposés sur fond profond,
// avec quelques étoiles. Plus contrasté que la prod (palette analogue).
function NebulaOrb({ hue, playing }: { hue: number; playing: boolean }) {
  const ps = playing ? "running" : "paused";
  const comp = (hue + 180) % 360;
  const stars = [
    { x: 24, y: 28, d: 0, dur: 1.7 },
    { x: 68, y: 22, d: 0.5, dur: 2.3 },
    { x: 56, y: 68, d: 1.1, dur: 1.9 },
    { x: 30, y: 74, d: 0.8, dur: 2.9 },
  ];
  return (
    <CandidateShell playing={playing} background={`radial-gradient(circle at 50% 40%, hsl(${hue} 45% 14%), #05060a 78%)`}>
      <div
        className="absolute rounded-full"
        style={{
          width: "78%",
          height: "70%",
          left: "2%",
          top: "10%",
          background: `radial-gradient(closest-side, hsl(${hue} 92% 62% / 0.85), transparent 70%)`,
          mixBlendMode: "screen",
          animation: "lorbNebulaA 7.9s ease-in-out -2.2s infinite",
          animationPlayState: ps,
        }}
      />
      <div
        className="absolute rounded-full"
        style={{
          width: "72%",
          height: "66%",
          left: "28%",
          top: "28%",
          background: `radial-gradient(closest-side, hsl(${comp} 85% 60% / 0.7), transparent 70%)`,
          mixBlendMode: "screen",
          animation: "lorbNebulaB 9.7s ease-in-out infinite",
          animationPlayState: ps,
        }}
      />
      {stars.map((s, i) => (
        <div
          key={i}
          className="absolute rounded-full bg-white"
          style={{
            width: 2,
            height: 2,
            left: `${s.x}%`,
            top: `${s.y}%`,
            animation: `orbTwinkle ${s.dur}s ease-in-out ${s.d}s infinite`,
            animationPlayState: ps,
          }}
        />
      ))}
    </CandidateShell>
  );
}

// Sonar : des anneaux naissent au centre et s'évanouissent vers le bord
// pendant que le cœur pulse -- l'orbe "émet" littéralement la voix.
function SonarOrb({ hue, playing }: { hue: number; playing: boolean }) {
  const ps = playing ? "running" : "paused";
  return (
    <CandidateShell playing={playing} background={`radial-gradient(circle at 35% 30%, hsl(${hue} 55% 38%), hsl(${hue} 60% 18%) 78%)`}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="absolute rounded-full"
          style={{
            inset: "6%",
            border: `2px solid hsl(${hue} 90% 72% / 0.8)`,
            animation: `lorbSonarRing 4.2s ease-out ${-i * 1.4}s infinite`,
            animationPlayState: ps,
          }}
        />
      ))}
      <div
        className="absolute rounded-full"
        style={{
          width: "34%",
          height: "34%",
          left: "33%",
          top: "33%",
          background: `radial-gradient(closest-side, white, hsl(${hue} 100% 82%) 45%, transparent 72%)`,
          animation: "lorbSonarCore 1.7s ease-in-out infinite",
          animationPlayState: ps,
        }}
      />
    </CandidateShell>
  );
}

// Lave : des gouttes lumineuses montent lentement du fond, se déforment et se
// dissolvent en haut -- matière lente et hypnotique, moins "électrique".
function LavaOrb({ hue, playing }: { hue: number; playing: boolean }) {
  const ps = playing ? "running" : "paused";
  const blobs = [
    { left: "-2%", w: 58, h: 50, d: 0 },
    { left: "30%", w: 48, h: 44, d: -2.6 },
    { left: "54%", w: 42, h: 40, d: -5.2 },
  ];
  return (
    <CandidateShell playing={playing} background={`linear-gradient(180deg, hsl(${hue} 70% 30%), hsl(${(hue + 20) % 360} 80% 13%))`}>
      <div
        className="absolute"
        style={{
          width: "110%",
          height: "45%",
          left: "-5%",
          bottom: "-18%",
          borderRadius: "50%",
          background: `radial-gradient(closest-side, hsl(${(hue + 15) % 360} 95% 62% / 0.9), transparent 75%)`,
        }}
      />
      {blobs.map((b, i) => (
        <div
          key={i}
          className="absolute rounded-full"
          style={{
            width: `${b.w}%`,
            height: `${b.h}%`,
            left: b.left,
            top: "26%",
            background: `radial-gradient(closest-side, hsl(${(hue + 15) % 360} 95% 64% / 0.85), transparent 70%)`,
            mixBlendMode: "screen",
            animation: `lorbLavaRise 7.8s ease-in-out ${b.d}s infinite`,
            animationPlayState: ps,
          }}
        />
      ))}
    </CandidateShell>
  );
}

// Couronne : l'inverse de la prod -- centre sombre (éclipse) et lumière
// vivant sur le bord, qui flare et scintille en tournant lentement.
function CoronaOrb({ hue, playing }: { hue: number; playing: boolean }) {
  const ps = playing ? "running" : "paused";
  const ringMask = "radial-gradient(closest-side, transparent 55%, black 68%, black 88%, transparent 96%)";
  return (
    <CandidateShell playing={playing} background={`radial-gradient(circle, hsl(${hue} 40% 9%) 0 42%, hsl(${hue} 55% 16%) 72%, hsl(${hue} 65% 26%))`}>
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: `radial-gradient(closest-side, transparent 52%, hsl(${hue} 95% 65% / 0.9) 72%, hsl(${(hue + 30) % 360} 95% 70% / 0.55) 80%, transparent 93%)`,
          animation: "lorbCoronaFlare 2.1s ease-in-out infinite",
          animationPlayState: ps,
        }}
      />
      <div className="absolute inset-0" style={{ animation: "lorbSpin 6.5s linear infinite", animationPlayState: ps }}>
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background:
              "conic-gradient(rgba(255,255,255,0) 0deg, rgba(255,255,255,0.5) 40deg, rgba(255,255,255,0) 90deg, rgba(255,255,255,0.35) 170deg, rgba(255,255,255,0) 230deg, rgba(255,255,255,0.45) 310deg, rgba(255,255,255,0) 360deg)",
            WebkitMask: ringMask,
            mask: ringMask,
            mixBlendMode: "screen",
          }}
        />
      </div>
    </CandidateShell>
  );
}

const CANDIDATE_VARIANTS: { title: string; desc: string; render: (h: number, p: boolean) => ReactNode }[] = [
  { title: "Comète", desc: "Un arc de lumière orbite sur le bord + étincelle contre-orbitale. Énergique, très lisible même en petit.", render: (h, p) => <CometOrb hue={h} playing={p} /> },
  { title: "Nébuleuse bichrome", desc: "Deux nuages complémentaires qui tourbillonnent en sens opposés + étoiles. Plus contrasté que la prod.", render: (h, p) => <NebulaOrb hue={h} playing={p} /> },
  { title: "Sonar", desc: "Des anneaux naissent au centre et partent vers le bord : l'orbe « émet » la voix. Sémantique audio forte.", render: (h, p) => <SonarOrb hue={h} playing={p} /> },
  { title: "Lave", desc: "Gouttes lumineuses qui montent et se dissolvent. Lent, hypnotique, moins « électrique ».", render: (h, p) => <LavaOrb hue={h} playing={p} /> },
  { title: "Couronne", desc: "Éclipse inversée : centre sombre, la lumière vit sur le bord et flare. Dramatique, très distinctif.", render: (h, p) => <CoronaOrb hue={h} playing={p} /> },
];

const CLOUD_VARIANTS: { title: string; desc: string; config: CloudConfig }[] = [
  { title: "Nuages — duo qui se relaie", desc: "2 nuages qui se cèdent la place en fondu, un qui s'estompe pendant que l'autre arrive.", config: CLOUD_TWO },
  { title: "Nuages — trio qui se relaie", desc: "3 nuages déphasés d'1/3 de cycle -- mélange plus riche.", config: CLOUD_THREE },
  { title: "Nuages — respiration", desc: "3 nuages à position fixe qui gonflent/s'effacent en alternance (pas de déplacement).", config: CLOUD_BLOOM },
  { title: "Nuages — courant continu", desc: "4 petits nuages à déphasage régulier -- flux plus continu, moins \"ping-pong\".", config: CLOUD_CURRENT },
];

export default function OrbLabPage() {
  return (
    <div className="min-h-screen bg-background p-10 text-foreground">
      <style>{KEYFRAMES}</style>
      <h1 className="mb-2 text-xl font-medium">Orb Lab — Orbe vivante (prod) + Glass Bubble + nuages + Aurora Ribbon</h1>
      <p className="mb-8 text-sm text-muted">
        La première carte est le composant de production actuel (VoiceOrb). Le reste du labo est
        conservé pour comparaison et expérimentations futures.
      </p>

      <h2 className="mb-4 text-lg font-medium">Orbe vivante — design en production (2026-07-18)</h2>
      <div className="mb-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <DesignCard
          title="Orbe vivante (prod)"
          desc="Nappes en dérive organique + cœur scintillant bi-fréquence + halo. Play = état « parle » ; sinon figée, désaturée."
          initialHue={HUE_PURPLE}
          render={(h, p) => <VoiceOrb hue={h} size={SIZE} active={p} />}
        />
      </div>

      <h2 className="mb-4 text-lg font-medium">Candidats — itération 2 (à trancher)</h2>
      <p className="mb-4 text-sm text-muted">
        5 directions volontairement différentes. Même règle que la prod : figé au repos
        (pose gelée, désaturée), vivant en lecture. Le candidat retenu recevrait le même
        branchement amplitude audio (--voice-amp) que la prod.
      </p>
      <div className="mb-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {CANDIDATE_VARIANTS.map(({ title, desc, render }) => (
          <DesignCard key={title} title={title} desc={desc} initialHue={HUE_PURPLE} render={render} />
        ))}
      </div>

      <h2 className="mb-4 text-lg font-medium">Glass Bubble — original</h2>
      <div className="mb-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <DesignCard
          title="Glass Bubble — original"
          desc="Reflet retiré. Play = lumière qui tourne vite + respiration."
          initialHue={HUE_PURPLE}
          render={(h, p) => <GlassBubbleOriginal hue={h} playing={p} />}
        />
      </div>

      <h2 className="mb-4 text-lg font-medium">Nuages qui se dispersent (remplace &quot;dérive large&quot;)</h2>
      <div className="mb-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {CLOUD_VARIANTS.map(({ title, desc, config }) => (
          <DesignCard
            key={title}
            title={title}
            desc={desc}
            initialHue={HUE_PURPLE}
            render={(h, p) => <CloudDisperse hue={h} playing={p} config={config} />}
          />
        ))}
      </div>

      <h2 className="mb-4 text-lg font-medium">Aurora Ribbon (inchangé)</h2>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <DesignCard
          title="13. Aurora Ribbon"
          desc="5 animations : orange=flicker, bleu=vague ample, rose=éclats, vert=vent, violet=ciel qui tourbillonne."
          initialHue={HUE_GREEN}
          render={(h, p) => <AuroraRibbon hue={h} playing={p} />}
        />
      </div>
    </div>
  );
}
