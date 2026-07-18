import { useMemo } from "react";
import type { CSSProperties, ReactNode } from "react";

type VoiceOrbProps = {
  /** Teinte 0-360, calculée en amont par golden-angle (cohérence catalogue/player/transcription). */
  hue: number;
  /** Taille du cercle en pixels. */
  size: number;
  className?: string;
  /** Contenu superposé au centre (icône play, spinner...). */
  children?: ReactNode;
  /** Voix en train de parler : nappes en dérive + cœur scintillant + halo,
   * intensité pilotée par l'amplitude audio réelle via var(--voice-amp)
   * (posée par PlayerProvider, repli 0.55 si aucune analyse ne tourne).
   * Figée sinon (défaut) : les animations restent posées mais en
   * animation-play-state:paused (zéro coût, reprise sans saut) et la var
   * n'est PAS référencée -- nécessaire pour rester léger avec 50-200 orbes
   * simultanées (transcription). */
  active?: boolean;
  /** Graine du mouvement. Défaut : dérivée de la teinte (donc déjà unique par
   * voix). Deux voix ne partagent ni les durées, ni les phases, ni les sens de
   * parcours, ni la géométrie exacte des nappes -- le mouvement est propre à
   * chaque voix, stable dans le temps (déterministe). */
  seed?: number;
};

// Intensité liée à l'amplitude : `lo + amp * (hi - lo)`, uniquement quand
// l'orbe est active (une orbe inactive ne doit pas dépendre de la var, sinon
// chaque écriture 60fps invaliderait le style des ~200 orbes de la
// transcription).
const amp = (lo: number, hi: number) => `calc(${lo} + var(--voice-amp, 0.55) * ${hi - lo})`;

// PRNG déterministe (mulberry32) : même seed -> même orbe, à jamais.
function mulberry32(a: number) {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Paramètres de mouvement/géométrie tirés du seed. Bornes choisies pour que
// toutes les combinaisons restent équilibrées (jamais de nappe hors champ ni
// de rythme absurde) ; les durées restent mutuellement incommensurables.
function buildOrbParams(seed: number) {
  const r = mulberry32(Math.round(seed * 1021) + 1);
  const f = (lo: number, hi: number) => lo + r() * (hi - lo);
  return {
    durBreathe: f(1.8, 2.5),
    durA: f(4.6, 7.4),
    durB: f(6.0, 9.4),
    durC: f(7.6, 11.2),
    durCore1: f(0.95, 1.35),
    durCore2: f(1.55, 2.2),
    durHalo: f(1.35, 1.9),
    delA: -f(0, 8),
    delB: -f(0, 10),
    delC: -f(0, 12),
    delCore1: -f(0, 1.5),
    delCore2: -f(0, 2.5),
    delHalo: -f(0, 1.8),
    revA: r() < 0.5,
    revB: r() < 0.5,
    revC: r() < 0.5,
    aInset: f(-16, -8),
    bW: f(78, 92),
    bH: f(56, 72),
    bL: f(2, 12),
    bT: f(12, 26),
    cSize: f(64, 76),
    hueA: f(20, 38),
    hueB: f(-34, -18),
  };
}

export default function VoiceOrb({ hue, size, className, children, active = false, seed }: VoiceOrbProps) {
  const playState = active ? "running" : "paused";
  // Mouvement + pose figée propres à la voix : tous les paramètres (durées,
  // phases, sens, géométrie) sortent d'un PRNG seedé -- stable pour une même
  // voix, différent d'une voix à l'autre.
  const p = useMemo(() => buildOrbParams(seed ?? hue), [seed, hue]);
  // En dessous de ~28px (transcription, casting) le détail est invisible :
  // une nappe de moins par instance.
  const small = size < 28;

  const anim = (name: string, durationS: number, delayS: number, reverse = false): CSSProperties => ({
    animation: `${name} ${durationS.toFixed(2)}s ease-in-out infinite`,
    animationDelay: `${delayS.toFixed(2)}s`,
    animationDirection: reverse ? "reverse" : undefined,
    animationPlayState: playState,
    willChange: active ? "transform, opacity" : undefined,
  });

  return (
    <span
      aria-hidden="true"
      className={`living-orb relative block shrink-0 ${className ?? ""}`}
      style={{ width: size, height: size }}
    >
      {/* Échelle liée à l'amplitude : englobe halo + sphère (le transform de la
          sphère est déjà occupé par la respiration keyframe). */}
      <span
        className="absolute inset-0 block"
        style={{
          transform: active ? `scale(${amp(0.97, 1.06)})` : undefined,
          transition: "transform 120ms ease-out",
          willChange: active ? "transform" : undefined,
        }}
      >
      {/* Halo : lumière qui déborde de l'orbe, uniquement quand la voix parle.
          3 couches : fondu d'état (500ms) > suivi d'amplitude (120ms) > pulsation. */}
      <span
        className="pointer-events-none absolute block rounded-full"
        style={{ inset: "-38%", opacity: active ? 1 : 0, transition: "opacity 500ms ease" }}
      >
        <span
          className="absolute inset-0 block rounded-full"
          style={{
            opacity: active ? amp(0.15, 1) : undefined,
            transition: "opacity 120ms linear",
          }}
        >
          <span
            className="absolute inset-0 block rounded-full"
            style={{
              background: `radial-gradient(closest-side, hsl(${hue} 90% 62% / 0.5), hsl(${hue} 90% 62% / 0) 72%)`,
              ...anim("orb-halo-pulse", p.durHalo, p.delHalo),
            }}
          />
        </span>
      </span>

      {/* Sphère clippée : terne au repos, saturée + en respiration en lecture. */}
      <span
        className="absolute inset-0 block overflow-hidden rounded-full"
        style={{
          background: `radial-gradient(circle at 32% 28%, hsl(${hue} 72% 58%), hsl(${hue} 78% 40%) 58%, hsl(${(hue + 18) % 360} 65% 24%) 100%)`,
          filter: active ? "saturate(1.12) brightness(1.05)" : "saturate(0.8) brightness(0.92)",
          transition: "filter 500ms ease",
          ...anim("orb-breathe", p.durBreathe, 0),
        }}
      >
        {/* Nappe large, teinte analogue chaude (décalage seedé) */}
        <span
          className="absolute block rounded-full"
          style={{
            inset: `${p.aInset.toFixed(1)}%`,
            background: `radial-gradient(closest-side, hsl(${(hue + p.hueA) % 360} 95% 66% / 0.9), hsl(${(hue + p.hueA) % 360} 95% 66% / 0) 68%)`,
            mixBlendMode: "screen",
            ...anim("orb-drift-a", p.durA, p.delA, p.revA),
          }}
        />
        {/* Nappe elliptique claire, teinte analogue froide (géométrie seedée --
            la rotation des keyframes n'a d'effet visible que sur une ellipse) */}
        <span
          className="absolute block"
          style={{
            width: `${p.bW.toFixed(1)}%`,
            height: `${p.bH.toFixed(1)}%`,
            left: `${p.bL.toFixed(1)}%`,
            top: `${p.bT.toFixed(1)}%`,
            borderRadius: "50%",
            background: `radial-gradient(closest-side, hsl(${(hue + p.hueB + 360) % 360} 92% 74% / 0.7), hsl(${(hue + p.hueB + 360) % 360} 92% 74% / 0) 70%)`,
            mixBlendMode: "screen",
            ...anim("orb-drift-b", p.durB, p.delB, p.revB),
          }}
        />
        {/* Contre-couleur discrète : richesse du mélange sans casser
            l'identité de teinte de la voix */}
        {!small && (
          <span
            className="absolute block rounded-full"
            style={{
              width: "70%",
              height: "70%",
              left: "15%",
              top: "15%",
              background: `radial-gradient(closest-side, hsl(${(hue + 180) % 360} 85% 60% / 0.5), hsl(${(hue + 180) % 360} 85% 60% / 0) 70%)`,
              mixBlendMode: "screen",
              ...anim("orb-drift-c", p.durC, p.delC, p.revC),
            }}
          />
        )}
        {/* Cœur lumineux : deux scintillements à périodes incommensurables ;
            leur somme paraît aléatoire, comme modulée par la voix. Presque
            éteint au repos. */}
        <span
          className="absolute inset-0 block"
          style={{
            opacity: active ? amp(0.35, 1) : 0.25,
            transition: `opacity ${active ? 150 : 500}ms ease`,
          }}
        >
          <span
            className="absolute block rounded-full"
            style={{
              width: `${p.cSize.toFixed(1)}%`,
              height: `${p.cSize.toFixed(1)}%`,
              left: `${((100 - p.cSize) / 2).toFixed(1)}%`,
              top: `${((100 - p.cSize) / 2).toFixed(1)}%`,
              background: `radial-gradient(closest-side, hsl(${hue} 100% 96% / 0.85), hsl(${hue} 100% 96% / 0) 65%)`,
              ...anim("orb-core-flicker", p.durCore1, p.delCore1),
            }}
          />
          <span
            className="absolute block rounded-full"
            style={{
              width: "46%",
              height: "46%",
              left: "27%",
              top: "27%",
              background: `radial-gradient(closest-side, hsl(${(hue + 40) % 360} 100% 92% / 0.9), hsl(${(hue + 40) % 360} 100% 92% / 0) 62%)`,
              mixBlendMode: "screen",
              ...anim("orb-core-flicker-2", p.durCore2, p.delCore2),
            }}
          />
        </span>
        {/* Finition sphérique : reflet zénithal + profondeur, proportionnels
            à la taille (l'orbe va de 16 à 160px). */}
        <span
          className="absolute inset-0 block rounded-full"
          style={{
            background:
              "linear-gradient(160deg, rgba(255,255,255,0.3), rgba(255,255,255,0.02) 42%, rgba(255,255,255,0.08) 100%)",
            boxShadow: `inset 0 ${size * 0.06}px ${size * 0.09}px rgba(255,255,255,0.4), inset 0 -${size * 0.1}px ${size * 0.14}px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(255,255,255,0.16)`,
          }}
        />
      </span>
      </span>
      {children && (
        <span className="absolute inset-0 z-10 flex items-center justify-center">{children}</span>
      )}
    </span>
  );
}
