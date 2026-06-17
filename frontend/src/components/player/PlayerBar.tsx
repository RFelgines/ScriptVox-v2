"use client";

import { usePlayer } from "./PlayerProvider";

const RATES = [0.5, 1, 1.25, 1.5, 2] as const;

function fmt(s: number): string {
  if (!isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function PlayerBar() {
  const { track, isPlaying, currentTime, duration, rate, toggle, seek, setRate, close } =
    usePlayer();

  if (!track) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 flex items-center gap-4 border-t border-gray-800 bg-gray-900 px-4 py-3">
      {/* Play / pause */}
      <button
        onClick={toggle}
        aria-label={isPlaying ? "Pause" : "Lire"}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-green-700 text-white hover:bg-green-600"
      >
        {isPlaying ? (
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
            <rect x="4" y="3" width="4" height="14" rx="1" />
            <rect x="12" y="3" width="4" height="14" rx="1" />
          </svg>
        ) : (
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
            <path d="M6 3.5l11 6.5-11 6.5V3.5z" />
          </svg>
        )}
      </button>

      {/* Titre */}
      <p className="w-40 shrink-0 truncate text-sm font-medium" title={track.title}>
        {track.title}
      </p>

      {/* Scrub */}
      <div className="flex flex-1 items-center gap-2 overflow-hidden">
        <span className="w-10 shrink-0 text-right text-xs text-gray-400">{fmt(currentTime)}</span>
        <input
          type="range"
          min={0}
          max={duration || 1}
          step={1}
          value={currentTime}
          onChange={(e) => seek(Number(e.target.value))}
          className="h-1 flex-1 cursor-pointer accent-green-500"
          aria-label="Progression"
        />
        <span className="w-10 shrink-0 text-xs text-gray-400">{fmt(duration)}</span>
      </div>

      {/* Vitesse */}
      <select
        value={rate}
        onChange={(e) => setRate(Number(e.target.value))}
        aria-label="Vitesse de lecture"
        className="rounded border border-gray-700 bg-gray-800 px-1.5 py-1 text-xs"
      >
        {RATES.map((r) => (
          <option key={r} value={r}>
            {r}×
          </option>
        ))}
      </select>

      {/* Fermer */}
      <button
        onClick={close}
        aria-label="Fermer le lecteur"
        className="shrink-0 text-gray-400 hover:text-gray-200"
      >
        ✕
      </button>
    </div>
  );
}
