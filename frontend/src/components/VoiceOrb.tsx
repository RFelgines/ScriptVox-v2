"use client";

import { useEffect, useRef } from "react";
import type { ReactNode, RefObject } from "react";

/** PRNG déterministe (même hue -> toujours le même mouvement) : chaque voix a
 * un "seed" figé (golden-angle), donc chaque orbe garde un comportement qui
 * lui est propre d'un rendu à l'autre sans avoir à stocker d'état. */
function seededRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

/** 3 harmoniques sommées par axe (amplitude décroissante, fréquences non
 * multiples entre elles) -- pas un chemin à N points fixes qu'on boucle, mais
 * une vraie fonction continue de type bruit fractal : le mouvement ne
 * retombe jamais perceptiblement sur lui-même et n'a pas de rythme constant. */
type Harmonic = { amp: number; freq: number; phase: number };

// Amplitudes exprimées en % du DIAMÈTRE DE L'ORBE (converties en px dans
// useOrganicDrift) -- pas en % de la taille propre de la tache. translate(%)
// en CSS est relatif à la boîte de l'élément qu'on anime ; comme chaque tache
// fait 62-84% de l'orbe (tailles différentes par tache), calibrer l'amplitude
// dans cette unité-là diluait et rendait incohérent le déplacement réel à
// l'écran d'une tache à l'autre (bug constaté : "amplitude trop faible,
// mouvement cantonné à une fraction de l'orbe").
function makeAxis(seed: number): [Harmonic, Harmonic, Harmonic] {
  return [
    { amp: 40 + seededRandom(seed) * 15, freq: 0.16 + seededRandom(seed + 1) * 0.1, phase: seededRandom(seed + 2) * Math.PI * 2 },
    { amp: 18 + seededRandom(seed + 3) * 10, freq: 0.3 + seededRandom(seed + 4) * 0.16, phase: seededRandom(seed + 5) * Math.PI * 2 },
    { amp: 7 + seededRandom(seed + 6) * 6, freq: 0.5 + seededRandom(seed + 7) * 0.25, phase: seededRandom(seed + 8) * Math.PI * 2 },
  ];
}

function evalAxis(harmonics: Harmonic[], t: number): number {
  return harmonics.reduce((sum, h) => sum + h.amp * Math.sin(h.freq * t + h.phase), 0);
}

type Axes = { x: [Harmonic, Harmonic, Harmonic]; y: [Harmonic, Harmonic, Harmonic] };

/** Anime les taches d'une orbe tant que `active` est vrai -- rAF direct sur
 * le style (pas de re-render React par frame). À l'arrêt, remet les taches à
 * leur position statique. Un seul cas concurrent réaliste (une voix survolée
 * ou un segment en lecture à la fois), donc le coût rAF reste négligeable.
 * `elRefs.current` est relu à CHAQUE frame (pas capturé une fois à la création
 * de l'effet) : si l'orbe est montée avec `active` déjà vrai dès le premier
 * rendu (ex. segment déjà en lecture), les <span> des taches ne sont pas
 * encore attachés au moment où l'effet démarre -- les capturer par valeur à
 * cet instant les figeait à `null` pour toujours (bug constaté : "plus
 * d'animation du tout"). En les relisant à chaque frame, le premier tick (au
 * prochain repaint, donc après que les refs soient posées) les trouve déjà bons. */
function useOrganicDrift(
  elRefs: RefObject<(HTMLSpanElement | null)[]>,
  axes: Axes[],
  orbSize: number,
  active: boolean,
) {
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!active) return;
    // Accessibilité : ce mouvement est piloté en JS, donc la règle CSS
    // `prefers-reduced-motion` du thème (qui mettait en pause les animations
    // CSS de l'ancienne orbe) ne peut plus l'arrêter. On la respecte ici.
    if (
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = (now - start) / 1000;
      const els = elRefs.current;
      axes.forEach((axis, i) => {
        const el = els[i];
        if (!el) return;
        // amplitude en % du diamètre de l'orbe -> px, pour un déplacement
        // cohérent quelle que soit la taille propre de la tache (voir makeAxis).
        const x = (evalAxis(axis.x, t) / 100) * orbSize;
        const y = (evalAxis(axis.y, t) / 100) * orbSize;
        el.style.transform = `translate(${x}px, ${y}px)`;
      });
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current);
      for (const el of elRefs.current) {
        if (el) el.style.transform = "";
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}

type VoiceOrbProps = {
  /** Teinte 0-360, calculée en amont par golden-angle (cohérence catalogue/player/transcription). */
  hue: number;
  /** Taille du cercle en pixels. */
  size: number;
  className?: string;
  /** Contenu superposé au centre (icône play, spinner...). */
  children?: ReactNode;
  /** Segment en cours de lecture / voix survolée : déclenche le mouvement.
   * Statique sinon (défaut) -- nécessaire pour rester léger avec 50-200
   * orbes simultanées (transcription de chapitre). */
  active?: boolean;
  /** "flat" (défaut) : dégradé radial doux façon ElevenLabs, sans effet de
   * verre ni ombres marquées -- voir mémoire voice-orb-redesign-elevenlabs.
   * "glass" : ancien rendu "bulle de verre" (conic-gradient tournant + reflets),
   * conservé pour comparaison/retour arrière, pas supprimé. */
  variant?: "flat" | "glass";
};

export default function VoiceOrb({
  hue,
  size,
  className,
  children,
  active = false,
  variant = "flat",
}: VoiceOrbProps) {
  // Position de base + harmoniques de mouvement dérivées (seed = hue) pour
  // que chaque voix ait un emplacement de tache et un mouvement qui lui sont
  // propres. Calculées avant le if/return pour que useOrganicDrift (hook)
  // soit toujours appelé au même rang, même si `variant` change entre deux
  // rendus (règle des hooks) -- coût négligeable quand variant="glass" ne
  // s'en sert pas.
  const hueWarm = (hue + 45) % 360;
  const hueCool = (hue + 200) % 360;
  // En dessous de ~28px (transcription 16px, casting 22px) la troisième tache
  // n'est plus discernable : on l'omet. Une nappe de moins par instance, ce qui
  // compte quand un chapitre affiche 50-200 orbes. Reprend le seuil que l'orbe
  // précédente appliquait déjà.
  const spotHues = size < 28 ? [hue, hueWarm] : [hue, hueWarm, hueCool];
  // Taches placées à ~120° les unes des autres autour du centre (avec jitter
  // d'angle/rayon par tache) -- avant, les 3 positions de base retombaient
  // toutes dans la moitié basse du cercle, donc les couleurs secondaires
  // (chaude/froide) semblaient collées en bas quel que soit la voix.
  const spots = spotHues.map((spotHue, i) => {
    const seed = hue * 12.9898 + i * 78.233;
    const angle = ((i * 120 + (seededRandom(seed) - 0.5) * 50) * Math.PI) / 180;
    const radius = 14 + seededRandom(seed + 1) * 12;
    const size = 62 + seededRandom(seed + 2) * 22;
    return {
      hue: spotHue,
      top: 50 + radius * Math.sin(angle) - size / 2,
      left: 50 + radius * Math.cos(angle) - size / 2,
      size,
      x: makeAxis(seed + 100),
      y: makeAxis(seed + 200),
    };
  });

  const elRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const axes: Axes[] = spots.map((spot) => ({ x: spot.x, y: spot.y }));
  useOrganicDrift(elRefs, axes, size, active && variant === "flat");

  if (variant === "glass") {
    return (
      <span
        aria-hidden="true"
        className={`relative block shrink-0 overflow-hidden rounded-full ${className ?? ""}`}
        style={{
          width: size,
          height: size,
          animation: active ? "orbGlassBreathe 1s ease-in-out infinite" : "none",
        }}
      >
        <span
          className="absolute -inset-4 block"
          style={{
            background: `conic-gradient(from 120deg, hsl(${hue} 85% 62%), hsl(${(hue + 70) % 360} 80% 58%), hsl(${(hue + 200) % 360} 75% 50%), hsl(${hue} 85% 62%))`,
            filter: "blur(14px)",
            animation: active ? "orbSpinSlow 2.2s linear infinite" : "none",
          }}
        />
        <span
          className="absolute inset-0 block rounded-full"
          style={{
            background:
              "linear-gradient(150deg, rgba(255,255,255,0.5), rgba(255,255,255,0.04) 40%, rgba(255,255,255,0.2) 100%)",
            backdropFilter: "blur(4px) saturate(1.3)",
            border: "1px solid rgba(255,255,255,0.4)",
            boxShadow:
              "inset 0 10px 16px rgba(255,255,255,0.45), inset 0 -16px 22px rgba(0,0,0,0.2), inset 6px 0 10px rgba(255,255,255,0.08)",
          }}
        />
        {children && (
          <span className="absolute inset-0 flex items-center justify-center">{children}</span>
        )}
      </span>
    );
  }

  // Flat (ElevenLabs) : 3 taches radiales douces sur une base unie -- pas de
  // bord dur, pas de verre, pas de pulsation de taille. Statique au repos ;
  // ne bouge (translate uniquement, piloté en JS -- voir useOrganicDrift)
  // que lorsque `active`.
  return (
    <span
      aria-hidden="true"
      className={`relative block shrink-0 overflow-hidden rounded-full ${className ?? ""}`}
      style={{
        width: size,
        height: size,
        background: `hsl(${hue} 70% 52%)`,
        boxShadow: "0 1px 1px rgba(0,0,0,0.05), 0 4px 10px rgba(0,0,0,0.08)",
      }}
    >
      {spots.map((spot, i) => (
        <span
          key={i}
          ref={(el) => {
            elRefs.current[i] = el;
          }}
          // Valeurs déterministes (fonction pure de `hue`, identiques serveur/client) --
          // le navigateur re-sérialise les floats et les couleurs hsl() après avoir
          // parsé le HTML SSR (arrondi, hsl()->rgb()), ce que React lit comme un
          // "mismatch" alors que le rendu est strictement identique.
          suppressHydrationWarning
          className="absolute block rounded-full"
          style={{
            top: `${spot.top}%`,
            left: `${spot.left}%`,
            width: `${spot.size}%`,
            height: `${spot.size}%`,
            background: `radial-gradient(circle, hsl(${spot.hue} 90% 65%) 0%, hsl(${spot.hue} 90% 65% / 0) 70%)`,
          }}
        />
      ))}
      {children && (
        <span className="absolute inset-0 flex items-center justify-center">{children}</span>
      )}
    </span>
  );
}
