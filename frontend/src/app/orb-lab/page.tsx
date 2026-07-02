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
import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";

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
      <h1 className="mb-2 text-xl font-medium">Orb Lab — Glass Bubble original + nuages qui se dispersent + Aurora Ribbon</h1>
      <p className="mb-8 text-sm text-muted">
        Original recréé fidèlement (conic-gradient qui tourne). &quot;Dérive large&quot; remplacée par
        4 variantes de nuages qui se cèdent la place -- transform + opacity uniquement, pas de flou.
      </p>

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
