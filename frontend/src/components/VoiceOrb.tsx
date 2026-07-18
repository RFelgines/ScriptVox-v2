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
};

// Intensité liée à l'amplitude : `lo + amp * (hi - lo)`, uniquement quand
// l'orbe est active (une orbe inactive ne doit pas dépendre de la var, sinon
// chaque écriture 60fps invaliderait le style des ~200 orbes de la
// transcription).
const amp = (lo: number, hi: number) => `calc(${lo} + var(--voice-amp, 0.55) * ${hi - lo})`;

export default function VoiceOrb({ hue, size, className, children, active = false }: VoiceOrbProps) {
  const playState = active ? "running" : "paused";
  // Phase déterministe par teinte : la pose figée diffère d'une voix à
  // l'autre (mais reste stable pour une même voix), et deux orbes actives
  // simultanément ne bougent pas en miroir.
  const phase = -(((hue % 360) + 360) % 360) * 13;
  // En dessous de ~28px (transcription, casting) le détail est invisible :
  // une nappe de moins par instance.
  const small = size < 28;

  const anim = (name: string, durationS: number, phaseScale: number): CSSProperties => ({
    animation: `${name} ${durationS}s ease-in-out infinite`,
    animationDelay: `${Math.round(phase * phaseScale)}ms`,
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
              ...anim("orb-halo-pulse", 1.6, 0.4),
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
          ...anim("orb-breathe", 2.1, 0),
        }}
      >
        {/* Nappe large, teinte analogue +28° */}
        <span
          className="absolute block rounded-full"
          style={{
            inset: "-12%",
            background: `radial-gradient(closest-side, hsl(${(hue + 28) % 360} 95% 66% / 0.9), hsl(${(hue + 28) % 360} 95% 66% / 0) 68%)`,
            mixBlendMode: "screen",
            ...anim("orb-drift-a", 5.9, 1),
          }}
        />
        {/* Nappe elliptique claire, teinte analogue -26° (la rotation des
            keyframes n'a d'effet visible que sur une forme non circulaire) */}
        <span
          className="absolute block"
          style={{
            width: "85%",
            height: "64%",
            left: "7.5%",
            top: "18%",
            borderRadius: "50%",
            background: `radial-gradient(closest-side, hsl(${(hue + 334) % 360} 92% 74% / 0.7), hsl(${(hue + 334) % 360} 92% 74% / 0) 70%)`,
            mixBlendMode: "screen",
            ...anim("orb-drift-b", 7.3, 1.7),
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
              ...anim("orb-drift-c", 9.1, 2.3),
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
              width: "68%",
              height: "68%",
              left: "16%",
              top: "16%",
              background: `radial-gradient(closest-side, hsl(${hue} 100% 96% / 0.85), hsl(${hue} 100% 96% / 0) 65%)`,
              ...anim("orb-core-flicker", 1.13, 0.6),
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
              ...anim("orb-core-flicker-2", 1.87, 1.1),
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
