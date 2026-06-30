"use client";

import type { CSSProperties } from "react";
import { ReactNode, useEffect, useRef, useState } from "react";
import { ChapterSummary, chapterAudioUrl, listChapters } from "@/lib/api";
import { usePlayer } from "./PlayerProvider";

const RATES = [0.5, 1, 1.25, 1.5, 2] as const;

function fmt(s: number): string {
  if (!isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function UtilBlock({
  onClick,
  disabled,
  ariaLabel,
  title,
  icon,
  label,
}: {
  onClick?: () => void;
  disabled?: boolean;
  ariaLabel: string;
  title?: string;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      title={title}
      className="flex flex-col items-center gap-1 rounded-control px-3 py-1.5 text-muted hover:bg-surface-2 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {icon}
      <span className="text-[11px]">{label}</span>
    </button>
  );
}

export default function PlayerBar() {
  const { track, isPlaying, currentTime, duration, rate, play, toggle, seek, setRate, close,
          currentSegment, voiceHues } = usePlayer();
  const [expanded, setExpanded] = useState(false);
  const [chaptersOpen, setChaptersOpen] = useState(false);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const rootRef = useRef<HTMLDivElement>(null);

  const bookId = track?.bookId;

  // Clic en dehors du bandeau (déplié) = replie le player.
  useEffect(() => {
    if (!expanded) return;
    function onMouseDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [expanded]);

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

  function skip(deltaSeconds: number) {
    const max = duration || Infinity;
    seek(Math.max(0, Math.min(currentTime + deltaSeconds, max)));
  }

  function cycleRate() {
    const idx = RATES.indexOf(rate as (typeof RATES)[number]);
    setRate(RATES[(idx + 1) % RATES.length]);
  }

  const remaining = duration > currentTime ? duration - currentTime : 0;

  const currentChapter = chapters.find((c) => c.position === track.chapterPosition);
  const chapterLabel =
    track.chapterPosition !== undefined
      ? currentChapter?.title ?? `Chapitre ${track.chapterPosition}`
      : null;

  return (
    <div ref={rootRef} className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-surface">
      {expanded && (
        <div className="flex max-h-[70vh] flex-col items-center gap-4 overflow-y-auto border-b border-border p-6">
          {track.coverUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={track.coverUrl}
              alt=""
              className="h-40 w-40 rounded-control object-cover shadow-lg sm:h-48 sm:w-48"
            />
          ) : (
            <div className="h-40 w-40 rounded-control bg-surface-2 sm:h-48 sm:w-48" />
          )}

          <div className="flex flex-col items-center gap-0.5 text-center">
            {chapterLabel && track.bookTitle && (
              <p className="text-xs text-muted">{track.bookTitle}</p>
            )}
            <p className="text-base font-semibold">{chapterLabel ?? track.title}</p>
          </div>

          {/* Scrub complet */}
          <div className="flex w-full max-w-md items-center gap-2">
            <span className="w-10 shrink-0 text-right text-xs text-muted">{fmt(currentTime)}</span>
            <input
              type="range"
              min={0}
              max={duration || 1}
              step="any"
              value={currentTime}
              onChange={(e) => seek(Number(e.target.value))}
              className="h-1 flex-1 cursor-pointer accent-primary"
              aria-label="Progression"
            />
            <span className="w-10 shrink-0 text-xs text-muted">{fmt(duration)}</span>
          </div>

          {/* Transport */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => hasPrev && playChapter(playable[currentIndex - 1])}
              disabled={!hasPrev}
              aria-label="Chapitre précédent"
              className="flex h-9 w-9 items-center justify-center rounded-control text-muted hover:bg-surface-2 hover:text-foreground disabled:opacity-30"
            >
              ⏮
            </button>

            <button
              onClick={() => skip(-15)}
              aria-label="Reculer de 15 secondes"
              className="relative flex h-9 w-9 items-center justify-center rounded-control text-muted hover:bg-surface-2 hover:text-foreground"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6 -scale-x-100">
                <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="absolute text-[8px] font-bold">15</span>
            </button>

            <button
              onClick={toggle}
              aria-label={isPlaying ? "Pause" : "Lire"}
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md transition-transform hover:scale-105 hover:opacity-90"
            >
              {isPlaying ? (
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                  <rect x="4" y="3" width="4" height="14" rx="1.5" />
                  <rect x="12" y="3" width="4" height="14" rx="1.5" />
                </svg>
              ) : (
                <svg viewBox="0 0 20 20" fill="currentColor" className="ml-0.5 h-5 w-5">
                  <path d="M6 3.5l11 6.5-11 6.5V3.5z" />
                </svg>
              )}
            </button>

            <button
              onClick={() => skip(15)}
              aria-label="Avancer de 15 secondes"
              className="relative flex h-9 w-9 items-center justify-center rounded-control text-muted hover:bg-surface-2 hover:text-foreground"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6">
                <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="absolute text-[8px] font-bold">15</span>
            </button>

            <button
              onClick={() => hasNext && playChapter(playable[currentIndex + 1])}
              disabled={!hasNext}
              aria-label="Chapitre suivant"
              className="flex h-9 w-9 items-center justify-center rounded-control text-muted hover:bg-surface-2 hover:text-foreground disabled:opacity-30"
            >
              ⏭
            </button>
          </div>

          {/* Rangée utilitaire */}
          <div className="flex items-center gap-2">
            <UtilBlock
              onClick={cycleRate}
              ariaLabel="Changer la vitesse de lecture"
              icon={<span className="text-sm font-semibold">{rate}×</span>}
              label="Vitesse"
            />
            {bookId && (
              <UtilBlock
                onClick={() => setChaptersOpen((v) => !v)}
                ariaLabel={chaptersOpen ? "Masquer les chapitres" : "Afficher les chapitres"}
                icon={<span className="text-base">☰</span>}
                label="Chapitres"
              />
            )}
            <UtilBlock
              disabled
              ariaLabel="Signet (bientôt disponible)"
              title="Signet — bientôt disponible"
              icon={
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4">
                  <path d="M5 3.5h10a.5.5 0 0 1 .5.5v13l-5.5-3.5L4.5 17V4a.5.5 0 0 1 .5-.5z" strokeLinejoin="round" />
                </svg>
              }
              label="Signet"
            />
          </div>

          {/* Liste des chapitres — masquée par défaut, dépliée via "Chapitres" */}
          {bookId && chaptersOpen && (
            <ul className="w-full max-w-md space-y-1 overflow-y-auto">
              {chapters.map((ch) => {
                const active = ch.position === track.chapterPosition;
                const playableCh = ch.status === "DONE";
                return (
                  <li key={ch.id}>
                    <button
                      onClick={() => playableCh && playChapter(ch)}
                      disabled={!playableCh}
                      className={`w-full rounded-control px-2 py-1.5 text-left text-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                        active
                          ? "bg-surface-2 font-medium text-foreground"
                          : "text-foreground/80 hover:bg-surface-2/60"
                      }`}
                    >
                      {ch.title ?? `Chapitre ${ch.position}`}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {!expanded && (
        <div className="flex items-center gap-2 px-4 pt-1.5">
          <span className="w-9 shrink-0 text-right text-[10px] text-muted">{fmt(currentTime)}</span>
          <input
            type="range"
            min={0}
            max={duration || 1}
            step="any"
            value={currentTime}
            onChange={(e) => seek(Number(e.target.value))}
            className="h-1 flex-1 cursor-pointer accent-primary"
            aria-label="Progression"
          />
          <span className="w-9 shrink-0 text-[10px] text-muted">
            {duration ? `-${fmt(remaining)}` : fmt(duration)}
          </span>
        </div>
      )}

      {/* Grille à 3 colonnes (1fr/auto/1fr) : le cluster central reste centré sur
          toute la largeur de la barre, quelle que soit la longueur du titre —
          un simple flex-1 sur le titre poussait le cluster contre le bord droit
          au lieu de le centrer. */}
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 py-2.5">
        {/* Colonne gauche : couverture + titre — clic = déplie/replie */}
        {!expanded ? (
          <button
            onClick={() => setExpanded(true)}
            className="flex min-w-0 items-center gap-2 justify-self-start text-left hover:text-muted"
            title={track.title}
          >
            {track.coverUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={track.coverUrl}
                alt=""
                className="h-9 w-9 shrink-0 rounded-control object-cover"
              />
            ) : (
              <div className="h-9 w-9 shrink-0 rounded-control bg-surface-2" />
            )}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5 shrink-0">
              <path d="M6 4l4 4-4 4" />
            </svg>
            <span className="truncate text-sm font-medium">{track.title}</span>
          </button>
        ) : (
          <button
            onClick={() => setExpanded(false)}
            className="flex min-w-0 items-center gap-1.5 justify-self-start text-left text-sm font-medium hover:text-muted"
            title={track.title}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5 shrink-0 rotate-90">
              <path d="M6 4l4 4-4 4" />
            </svg>
            <span className="truncate">{track.title}</span>
          </button>
        )}

        {/* Colonne centrale : cluster (replié uniquement — vide en déplié, où
            ces contrôles sont déjà affichés en plus grand dans le panneau). */}
        <div className="flex shrink-0 items-center gap-1.5 justify-self-center">
          {!expanded && (
            <>
              <button
                disabled
                aria-label="Signet (bientôt disponible)"
                title="Signet — bientôt disponible"
                className="flex h-8 w-8 items-center justify-center rounded-control text-muted opacity-40 disabled:cursor-not-allowed"
              >
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4">
                  <path d="M5 3.5h10a.5.5 0 0 1 .5.5v13l-5.5-3.5L4.5 17V4a.5.5 0 0 1 .5-.5z" strokeLinejoin="round" />
                </svg>
              </button>

              <button
                onClick={() => skip(-15)}
                aria-label="Reculer de 15 secondes"
                className="relative flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-surface-2 hover:text-foreground"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5 -scale-x-100">
                  <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                  <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="absolute text-[7px] font-bold">15</span>
              </button>

              <button
                onClick={toggle}
                aria-label={isPlaying ? "Pause" : "Lire"}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md transition-transform hover:scale-105 hover:opacity-90"
              >
                {isPlaying ? (
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                    <rect x="4" y="3" width="4" height="14" rx="1.5" />
                    <rect x="12" y="3" width="4" height="14" rx="1.5" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 20 20" fill="currentColor" className="ml-0.5 h-4 w-4">
                    <path d="M6 3.5l11 6.5-11 6.5V3.5z" />
                  </svg>
                )}
              </button>

              <button
                onClick={() => skip(15)}
                aria-label="Avancer de 15 secondes"
                className="relative flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-surface-2 hover:text-foreground"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
                  <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                  <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="absolute text-[7px] font-bold">15</span>
              </button>

              <select
                value={rate}
                onChange={(e) => setRate(Number(e.target.value))}
                aria-label="Vitesse de lecture"
                className="rounded-control border border-border bg-surface-2 px-1.5 py-1 text-xs text-foreground"
              >
                {RATES.map((r) => (
                  <option key={r} value={r}>
                    {r}×
                  </option>
                ))}
              </select>
            </>
          )}
        </div>

        {/* Colonne droite : "Lu par" + fermer */}
        <div className="flex items-center gap-2 justify-self-end overflow-hidden">
          {currentSegment !== null && (
            <div className="hidden sm:flex items-center gap-1.5 overflow-hidden">
              {currentSegment.voice_id && (
                <div
                  style={{
                    "--orb-c1": `hsl(${voiceHues.get(currentSegment.voice_id) ?? 0} 91% 65%)`,
                    "--orb-c2": `hsl(${((voiceHues.get(currentSegment.voice_id) ?? 0) + 59) % 360} 81% 60%)`,
                    "--orb-c3": `hsl(${((voiceHues.get(currentSegment.voice_id) ?? 0) + 347) % 360} 90% 66%)`,
                  } as CSSProperties}
                  className="voice-orb h-6 w-6 shrink-0 rounded-full shadow"
                  aria-hidden="true"
                />
              )}
              <div className="flex flex-col leading-tight overflow-hidden">
                <span className="text-[9px] uppercase tracking-wide text-muted/60">Lu par</span>
                <span className="truncate text-xs font-medium text-muted max-w-28">
                  {currentSegment.character_name ?? "Narrateur"}
                </span>
              </div>
            </div>
          )}
          <button
            onClick={close}
            aria-label="Fermer le lecteur"
            className="shrink-0 text-muted hover:text-foreground"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
