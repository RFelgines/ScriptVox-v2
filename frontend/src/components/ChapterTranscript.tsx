"use client";

import { useEffect, useRef, useState } from "react";
import { SegmentSummary, getChapterSegments, regenerateSegment } from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import VoiceOrb from "@/components/VoiceOrb";
import { useT } from "@/lib/i18n/LanguageContext";

// Un chapitre peut avoir 50-200+ segments rendus simultanément dans la liste
// scrollable ci-dessous. VoiceOrb est du CSS pur (plus de contexte WebGL) mais
// on garde le montage paresseux par IntersectionObserver : seul le segment
// visible + actif a besoin du rendu complet, les autres affichent un point de
// couleur unie le temps d'entrer dans la zone.
function LazySegmentOrb({ hue, active, root }: { hue: number; active: boolean; root: HTMLDivElement | null }) {
  const anchorRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = anchorRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { root, rootMargin: "200px 0px", threshold: 0 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [root]);

  return (
    <div ref={anchorRef} className="mt-0.5 h-4 w-4 shrink-0">
      {visible ? (
        <VoiceOrb hue={hue} size={16} active={active} />
      ) : (
        <div
          className="h-4 w-4 rounded-full"
          style={{ backgroundColor: `hsl(${hue} 91% 65%)` }}
          aria-hidden="true"
        />
      )}
    </div>
  );
}

interface Props {
  bookId: number;
  chapterPosition: number;
  chapterDone?: boolean;
}

export default function ChapterTranscript({ bookId, chapterPosition, chapterDone }: Props) {
  const t = useT();
  const { currentSegment, voiceHues, seek, isPlaying } = usePlayer();
  const [segments, setSegments] = useState<SegmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [regeneratingId, setRegeneratingId] = useState<number | null>(null);
  const currentRef = useRef<HTMLDivElement | null>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => { if (active) setLoading(true); });
    getChapterSegments(bookId, chapterPosition)
      .then((segs) => { if (active) { setSegments(segs); setLoading(false); } })
      .catch(() => { if (active) { setSegments([]); setLoading(false); } });
    return () => { active = false; };
  }, [bookId, chapterPosition]);

  // Auto-scroll au segment courant
  useEffect(() => {
    currentRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [currentSegment?.id]);

  const hasTiming = segments.some((s) => s.audio_offset_ms !== null);

  if (loading) {
    return (
      <div className="mt-6 animate-pulse rounded-2xl bg-surface p-4 text-sm text-muted shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)]">
        {t.player.transcript.loading}
      </div>
    );
  }

  if (segments.length === 0) {
    return (
      <div className="mt-6 rounded-2xl bg-surface p-4 text-sm text-muted shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)]">
        {t.player.transcript.empty}
      </div>
    );
  }

  return (
    <div className="mt-6 overflow-hidden rounded-2xl bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)]">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <p className="flex items-center gap-1.5 font-display text-sm font-medium">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          {t.player.transcript.title(chapterPosition)}
        </p>
        {!hasTiming && (
          <p className="text-xs text-warning">
            {t.player.transcript.syncUnavailable}
          </p>
        )}
      </div>

      {/* Plus de scroll propre ici : le vrai conteneur scrollable est le
          panneau déplié de PlayerBar -- éviter le scroll-dans-scroll (audit
          UI/UX 2026-07-03). `scrollRoot` (non clippant désormais) reste passé
          en `root` à l'IntersectionObserver de LazySegmentOrb : sans clip
          propre, la spec IntersectionObserver retombe sur le rect de cet
          élément intersecté avec les ancêtres qui clippent réellement (donc
          le panneau scrollable), le calcul de visibilité reste donc correct. */}
      <div ref={setScrollRoot}>
        {segments.map((seg) => {
          const isCurrent = currentSegment?.id === seg.id;
          const voiceId = seg.voice_id;
          const hue = voiceId ? (voiceHues.get(voiceId) ?? 0) : null;
          const label = seg.character_name ?? t.player.narrator;
          const canSeek = seg.audio_offset_ms !== null;

          function seekToSegment() {
            if (seg.audio_offset_ms !== null) seek(seg.audio_offset_ms / 1000);
          }

          function handleRegenerate(e: MouseEvent) {
            e.stopPropagation();
            setRegeneratingId(seg.id);
            regenerateSegment(bookId, chapterPosition, seg.id, {
              voice_id: seg.voice_id ?? "narrator",
            }).finally(() => setRegeneratingId(null));
          }

          return (
            <div
              key={seg.id}
              ref={isCurrent ? currentRef : null}
              role={canSeek ? "button" : undefined}
              tabIndex={canSeek ? 0 : undefined}
              onClick={canSeek ? seekToSegment : undefined}
              onKeyDown={
                canSeek
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        seekToSegment();
                      }
                    }
                  : undefined
              }
              aria-label={canSeek ? t.player.transcript.seekAriaLabel(label) : undefined}
              className={`group flex gap-3 border-b border-border/50 px-4 py-2.5 transition-colors last:border-0 ${
                canSeek ? "cursor-pointer" : ""
              } ${isCurrent ? "border-l-2" : "hover:bg-surface-2/40"}`}
              style={
                isCurrent
                  ? {
                      backgroundColor: "var(--transcript-highlight-bg)",
                      borderLeftColor: "var(--transcript-highlight-border)",
                    }
                  : undefined
              }
            >
              {/* Indicateur de voix */}
              <div className="flex w-28 shrink-0 items-start gap-1.5 pt-0.5">
                {hue !== null ? (
                  <LazySegmentOrb hue={hue} active={isCurrent && isPlaying} root={scrollRoot} />
                ) : (
                  <div className="mt-0.5 h-4 w-4 shrink-0 rounded-full bg-surface-2" aria-hidden="true" />
                )}
                <span
                  className={`truncate text-xs leading-relaxed ${
                    isCurrent ? "font-medium text-foreground" : "text-muted"
                  }`}
                  title={label}
                >
                  {label}
                </span>
              </div>

              {/* Texte du segment */}
              <p
                className={`flex-1 text-sm leading-relaxed ${
                  isCurrent ? "font-medium text-foreground" : "text-foreground/80"
                }`}
              >
                {seg.segment_type === "DIALOGUE" ? seg.text : (
                  <span className="italic">{seg.text}</span>
                )}
              </p>

              {/* Bouton régénérer (uniquement si chapitre DONE) */}
              {chapterDone && (
                <button
                  onClick={handleRegenerate}
                  disabled={regeneratingId === seg.id}
                  aria-label="Regénérer ce segment"
                  title="Regénérer ce segment"
                  className="ml-1 shrink-0 self-center rounded-full p-1 text-muted opacity-0 transition-opacity hover:bg-surface-2 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 group-hover:opacity-100"
                >
                  {regeneratingId === seg.id ? (
                    <span className="block h-3.5 w-3.5 text-[10px] leading-none">…</span>
                  ) : (
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                      <path d="M13.5 8A5.5 5.5 0 1 1 8 2.5" />
                      <path d="M13.5 2.5v3.5h-3.5" />
                    </svg>
                  )}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
