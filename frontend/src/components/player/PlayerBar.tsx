"use client";

import { useEffect, useState } from "react";
import { ChapterSummary, chapterAudioUrl, listChapters } from "@/lib/api";
import { usePlayer } from "./PlayerProvider";

const RATES = [0.5, 1, 1.25, 1.5, 2] as const;

function fmt(s: number): string {
  if (!isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function PlayerBar() {
  const { track, isPlaying, currentTime, duration, rate, play, toggle, seek, setRate, close } =
    usePlayer();
  const [expanded, setExpanded] = useState(false);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);

  const bookId = track?.bookId;

  useEffect(() => {
    if (!expanded || !bookId) return;
    let active = true;
    listChapters(bookId).then((chs) => {
      if (active) setChapters(chs);
    });
    return () => {
      active = false;
    };
  }, [expanded, bookId]);

  if (!track) return null;

  function playChapter(ch: ChapterSummary) {
    if (!bookId || !track) return;
    play({
      title: `${track.bookTitle ?? track.title} — ${ch.title ?? `Chapitre ${ch.position}`}`,
      src: chapterAudioUrl(bookId, ch.position),
      bookId,
      bookTitle: track.bookTitle,
      coverUrl: track.coverUrl,
      chapterPosition: ch.position,
    });
  }

  // Navigation prev/next limitée aux chapitres DONE (audio réellement disponible).
  const playable = chapters.filter((c) => c.status === "DONE");
  const currentIndex = playable.findIndex((c) => c.position === track.chapterPosition);
  const hasPrev = track.chapterPosition !== undefined && currentIndex > 0;
  const hasNext =
    track.chapterPosition !== undefined &&
    currentIndex >= 0 &&
    currentIndex < playable.length - 1;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-gray-800 bg-gray-900">
      {expanded && (
        <div className="flex max-h-80 flex-col gap-3 border-b border-gray-800 p-4 sm:flex-row">
          <div className="flex shrink-0 items-center gap-3 sm:flex-col sm:items-start">
            {track.coverUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={track.coverUrl}
                alt=""
                className="h-20 w-14 shrink-0 rounded object-cover sm:h-32 sm:w-20"
              />
            ) : (
              <div className="h-20 w-14 shrink-0 rounded bg-gray-800 sm:h-32 sm:w-20" />
            )}
            <div className="flex items-center gap-2">
              <button
                onClick={() => hasPrev && playChapter(playable[currentIndex - 1])}
                disabled={!hasPrev}
                aria-label="Chapitre précédent"
                className="rounded px-2 py-1 text-gray-400 hover:bg-gray-800 hover:text-gray-100 disabled:opacity-30"
              >
                ⏮
              </button>
              <button
                onClick={() => hasNext && playChapter(playable[currentIndex + 1])}
                disabled={!hasNext}
                aria-label="Chapitre suivant"
                className="rounded px-2 py-1 text-gray-400 hover:bg-gray-800 hover:text-gray-100 disabled:opacity-30"
              >
                ⏭
              </button>
            </div>
          </div>

          {bookId ? (
            <ul className="flex-1 space-y-1 overflow-y-auto">
              {chapters.map((ch) => {
                const active = ch.position === track.chapterPosition;
                const playableCh = ch.status === "DONE";
                return (
                  <li key={ch.id}>
                    <button
                      onClick={() => playableCh && playChapter(ch)}
                      disabled={!playableCh}
                      className={`w-full rounded px-2 py-1.5 text-left text-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                        active
                          ? "bg-gray-800 text-amber-400"
                          : "text-gray-300 hover:bg-gray-800/60"
                      }`}
                    >
                      {ch.title ?? `Chapitre ${ch.position}`}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="flex-1 text-sm text-gray-500">{track.title}</p>
          )}
        </div>
      )}

      <div className="flex items-center gap-4 px-4 py-3">
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

        {/* Titre — clic = déplie/replie */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-40 shrink-0 truncate text-left text-sm font-medium hover:text-gray-300"
          title={track.title}
        >
          {expanded ? "▾ " : "▸ "}
          {track.title}
        </button>

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
    </div>
  );
}
