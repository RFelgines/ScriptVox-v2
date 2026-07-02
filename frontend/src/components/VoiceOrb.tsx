import type { ReactNode } from "react";

type VoiceOrbProps = {
  /** Teinte 0-360, calculée en amont par golden-angle (cohérence catalogue/player/transcription). */
  hue: number;
  /** Taille du cercle en pixels. */
  size: number;
  className?: string;
  /** Contenu superposé au centre (icône play, spinner...). */
  children?: ReactNode;
  /** Segment en cours de lecture / voix survolée : déclenche la rotation rapide
   * + respiration. Statique sinon (défaut) -- nécessaire pour rester léger avec
   * 50-200 orbes simultanées (transcription de chapitre). */
  active?: boolean;
};

export default function VoiceOrb({ hue, size, className, children, active = false }: VoiceOrbProps) {
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
