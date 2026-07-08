"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { ChapterSummary, chapterAudioUrl, listChapters } from "@/lib/api";
import { usePlayer } from "./PlayerProvider";
import VoiceOrb from "@/components/VoiceOrb";
import ChapterTranscript from "@/components/ChapterTranscript";
import Select from "@/components/ui/Select";
import { useT } from "@/lib/i18n/LanguageContext";

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
      className="flex flex-col items-center gap-1 rounded-2xl px-3.5 py-2 text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
    >
      {icon}
      <span className="text-[11px]">{label}</span>
    </button>
  );
}

export default function PlayerBar() {
  const t = useT();
  const { track, isPlaying, currentTime, duration, rate, play, toggle, seek, setRate, close,
          currentSegment, voiceHues, voiceNames } = usePlayer();
  const [expanded, setExpanded] = useState(false);
  const [chaptersOpen, setChaptersOpen] = useState(false);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [coverOk, setCoverOk] = useState(true);
  const rootRef = useRef<HTMLDivElement>(null);

  const bookId = track?.bookId;

  // Reset le fallback à chaque nouvelle piste -- une couverture cassée sur le
  // morceau précédent ne doit pas s'appliquer au suivant. setState différé en
  // microtâche (règle react-hooks/set-state-in-effect, même convention
  // qu'ailleurs dans ce projet).
  useEffect(() => {
    Promise.resolve().then(() => setCoverOk(true));
  }, [track?.coverUrl]);

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
    listChapters(bookId)
      .then((chs) => {
        if (active) setChapters(chs);
      })
      .catch(() => {
        if (active) setChapters([]);
      });
    return () => {
      active = false;
    };
  }, [expanded, bookId]);

  if (!track) return null;

  function playChapter(ch: ChapterSummary) {
    if (!bookId || !track) return;
    play({
      title: `${track.bookTitle ?? track.title} — ${ch.title ?? t.book.chapterFallback(ch.position)}`,
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
      ? currentChapter?.title ?? t.book.chapterFallback(track.chapterPosition)
      : null;

  return (
    <div
      ref={rootRef}
      className="fixed right-0 bottom-0 left-0 z-50 bg-surface shadow-[0_-8px_24px_-8px_rgba(0,0,0,0.5),0_-1px_0_rgba(245,243,241,0.04)]"
    >
      {expanded && (
        // flex-col + overflow-hidden sur le conteneur, scroll délégué au SEUL
        // bloc "contenu déroulant" ci-dessous (chapitres + transcription) --
        // en-tête (couverture/scrub/transport) toujours visible, ne défile pas.
        // Avant : ce conteneur ET la transcription (ChapterTranscript) avaient
        // chacun leur propre overflow-y-auto, un scroll-dans-scroll qui se
        // volait les gestes tactiles en mobile (audit UI/UX 2026-07-03).
        // transition d'entrée seule (starting:, Tailwind v4) -- apparaissait
        // sans mouvement avant (même constat que la section Casting).
        <div className="flex max-h-[70vh] flex-col overflow-hidden border-b border-border transition-all duration-200 ease-out starting:translate-y-2 starting:opacity-0">
        <div className="flex flex-col items-center gap-4 p-6 pb-0">
          {track.coverUrl && coverOk ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={track.coverUrl}
              alt=""
              className="h-40 w-40 rounded-2xl object-cover shadow-[0_20px_40px_-12px_rgba(0,0,0,0.7),0_0_0_1px_rgba(245,243,241,0.05)] sm:h-48 sm:w-48"
              onError={() => setCoverOk(false)}
            />
          ) : (
            <div className="h-40 w-40 rounded-2xl bg-surface-2 sm:h-48 sm:w-48" />
          )}

          <div className="flex flex-col items-center gap-0.5 text-center">
            {chapterLabel && track.bookTitle && (
              <p className="text-xs text-muted">{track.bookTitle}</p>
            )}
            <p className="text-base font-semibold">{chapterLabel ?? track.title}</p>
          </div>

          {/* Scrub complet */}
          <div className="flex w-full max-w-md items-center gap-2">
            <span className="w-10 shrink-0 text-right font-mono text-xs tabular-nums text-muted">{fmt(currentTime)}</span>
            <input
              type="range"
              min={0}
              max={duration || 1}
              step="any"
              value={currentTime}
              onChange={(e) => seek(Number(e.target.value))}
              className="h-1 flex-1 cursor-pointer accent-primary"
              aria-label={t.player.progressAriaLabel}
            />
            <span className="w-10 shrink-0 font-mono text-xs tabular-nums text-muted">{fmt(duration)}</span>
          </div>

          {/* Transport */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => hasPrev && playChapter(playable[currentIndex - 1])}
              disabled={!hasPrev}
              aria-label={t.player.prevChapterAriaLabel}
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:opacity-50"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                <path d="M6 4a1 1 0 0 0-1 1v10a1 1 0 1 0 2 0v-4.1l7.4 4.94A1 1 0 0 0 16 15V5a1 1 0 0 0-1.6-.8L7 8.1V5a1 1 0 0 0-1-1z" />
              </svg>
            </button>

            <button
              onClick={() => skip(-15)}
              aria-label={t.player.rewind15AriaLabel}
              className="relative flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6 -scale-x-100">
                <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="absolute text-[10px] font-bold">15</span>
            </button>

            <button
              onClick={toggle}
              aria-label={isPlaying ? t.player.pauseAriaLabel : t.player.playAriaLabel}
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
              aria-label={t.player.forward15AriaLabel}
              className="relative flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6">
                <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="absolute text-[10px] font-bold">15</span>
            </button>

            <button
              onClick={() => hasNext && playChapter(playable[currentIndex + 1])}
              disabled={!hasNext}
              aria-label={t.player.nextChapterAriaLabel}
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:opacity-50"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                <path d="M14 4a1 1 0 0 1 1 1v10a1 1 0 1 1-2 0v-4.1l-7.4 4.94A1 1 0 0 1 4 15V5a1 1 0 0 1 1.6-.8L13 8.1V5a1 1 0 0 1 1-1z" />
              </svg>
            </button>
          </div>

          {/* Rangée utilitaire */}
          <div className="flex items-center gap-2">
            <UtilBlock
              onClick={cycleRate}
              ariaLabel={t.player.rateAriaLabel}
              icon={<span className="text-sm font-semibold">{rate}×</span>}
              label={t.player.rateLabel}
            />
            {bookId && (
              <UtilBlock
                onClick={() => setChaptersOpen((v) => !v)}
                ariaLabel={chaptersOpen ? t.player.hideChaptersAriaLabel : t.player.showChaptersAriaLabel}
                icon={
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="h-4 w-4">
                    <path d="M3 5.5h14M3 10h14M3 14.5h14" />
                  </svg>
                }
                label={t.player.chaptersLabel}
              />
            )}
            <UtilBlock
              disabled
              ariaLabel={t.player.bookmarkAriaLabel}
              title={t.player.bookmarkTitle}
              icon={
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4">
                  <path d="M5 3.5h10a.5.5 0 0 1 .5.5v13l-5.5-3.5L4.5 17V4a.5.5 0 0 1 .5-.5z" strokeLinejoin="round" />
                </svg>
              }
              label={t.player.bookmarkLabel}
            />
          </div>
        </div>

        {/* Seul bloc scrollable du panneau déplié -- chapitres + transcription. */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6 pt-4">
          <div className="mx-auto flex w-full max-w-md flex-col items-center gap-4">
            {/* Liste des chapitres — masquée par défaut, dépliée via "Chapitres" */}
            {bookId && chaptersOpen && (
              <ul className="w-full space-y-1 transition-all duration-200 ease-out starting:translate-y-1 starting:opacity-0">
                {chapters.map((ch) => {
                  const active = ch.position === track.chapterPosition;
                  const playableCh = ch.status === "DONE";
                  return (
                    <li key={ch.id}>
                      <button
                        onClick={() => playableCh && playChapter(ch)}
                        disabled={!playableCh}
                        className={`w-full rounded-xl px-3 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          active
                            ? "bg-surface-2 font-medium text-foreground"
                            : "text-foreground/80 hover:bg-surface-2/60"
                        }`}
                      >
                        {ch.title ?? t.book.chapterFallback(ch.position)}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            {bookId && track.chapterPosition !== undefined && (
              <div className="w-full">
                <ChapterTranscript bookId={bookId} chapterPosition={track.chapterPosition} />
              </div>
            )}
          </div>
        </div>
        </div>
      )}

      {!expanded && (
        <div className="flex items-center gap-2 px-4 pt-1.5">
          <span className="w-9 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted">{fmt(currentTime)}</span>
          <input
            type="range"
            min={0}
            max={duration || 1}
            step="any"
            value={currentTime}
            onChange={(e) => seek(Number(e.target.value))}
            className="h-1 flex-1 cursor-pointer accent-primary"
            aria-label={t.player.progressAriaLabel}
          />
          <span className="w-9 shrink-0 font-mono text-[10px] tabular-nums text-muted">
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
            className="flex w-full min-w-0 items-center gap-2 text-left hover:text-muted"
            title={track.title}
          >
            {track.coverUrl && coverOk ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={track.coverUrl}
                alt=""
                className="h-9 w-9 shrink-0 rounded-lg object-cover"
                onError={() => setCoverOk(false)}
              />
            ) : (
              <div className="h-9 w-9 shrink-0 rounded-lg bg-surface-2" />
            )}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5 shrink-0">
              <path d="M6 4l4 4-4 4" />
            </svg>
            <span className="min-w-0 truncate text-sm font-medium">{track.title}</span>
          </button>
        ) : (
          <button
            onClick={() => setExpanded(false)}
            className="flex w-full min-w-0 items-center gap-1.5 text-left text-sm font-medium hover:text-muted"
            title={track.title}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5 shrink-0 rotate-90">
              <path d="M6 4l4 4-4 4" />
            </svg>
            <span className="min-w-0 truncate">{track.title}</span>
          </button>
        )}

        {/* Colonne centrale : cluster (replié uniquement — vide en déplié, où
            ces contrôles sont déjà affichés en plus grand dans le panneau). */}
        <div className="flex shrink-0 items-center gap-1.5 justify-self-center">
          {!expanded && (
            <>
              {/* Masqué sous sm : le titre du morceau n'a plus de place visible
                  à 375px avec ce cluster au complet (mesuré à 0px de largeur
                  visible, audit UI/UX 2026-07-03) -- ce placeholder désactivé
                  reste disponible dans le panneau déplié. */}
              <button
                disabled
                aria-label={t.player.bookmarkAriaLabel}
                title={t.player.bookmarkTitle}
                className="hidden h-8 w-8 items-center justify-center rounded-full text-muted opacity-40 disabled:cursor-not-allowed sm:flex"
              >
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4">
                  <path d="M5 3.5h10a.5.5 0 0 1 .5.5v13l-5.5-3.5L4.5 17V4a.5.5 0 0 1 .5-.5z" strokeLinejoin="round" />
                </svg>
              </button>

              <button
                onClick={() => skip(-15)}
                aria-label={t.player.rewind15AriaLabel}
                className="relative flex h-8 w-8 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5 -scale-x-100">
                  <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                  <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="absolute text-[10px] font-bold">15</span>
              </button>

              <button
                onClick={toggle}
                aria-label={isPlaying ? t.player.pauseAriaLabel : t.player.playAriaLabel}
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
                aria-label={t.player.forward15AriaLabel}
                className="relative flex h-8 w-8 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
                  <path d="M12 5a7 7 0 1 0 6.06 3.5" strokeLinecap="round" />
                  <path d="M18 2.5v4.5h-4.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="absolute text-[10px] font-bold">15</span>
              </button>

              <Select
                value={String(rate)}
                onChange={(v) => setRate(Number(v))}
                ariaLabel={t.player.rateSelectAriaLabel}
                className="hidden sm:inline-block"
                options={RATES.map((r) => ({ value: String(r), label: `${r}×` }))}
              />
            </>
          )}
        </div>

        {/* Colonne droite : "Lu par" + fermer */}
        <div className="flex items-center gap-2 justify-self-end overflow-hidden">
          {currentSegment !== null && (
            <div className="hidden sm:flex items-center gap-1.5 overflow-hidden">
              {currentSegment.voice_id && (
                <VoiceOrb
                  hue={voiceHues.get(currentSegment.voice_id) ?? 0}
                  size={24}
                  className="shadow"
                  active={isPlaying}
                />
              )}
              <div className="flex flex-col leading-tight overflow-hidden">
                <span className="text-[10px] uppercase tracking-wide text-muted/60">{t.player.readByLabel}</span>
                <span className="truncate text-xs font-medium text-muted max-w-28">
                  {currentSegment.voice_id === "narrator"
                    ? t.player.narrator
                    : (currentSegment.voice_id && voiceNames.get(currentSegment.voice_id)) ??
                      currentSegment.character_name ??
                      t.player.narrator}
                </span>
              </div>
            </div>
          )}
          <button
            onClick={close}
            aria-label={t.player.closePlayerAriaLabel}
            className="shrink-0 text-muted hover:text-foreground"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
