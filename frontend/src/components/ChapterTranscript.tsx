"use client";

import { useEffect, useRef, useState } from "react";
import { SegmentSummary, getChapterSegments } from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import VoiceOrb from "@/components/VoiceOrb";

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
}

export default function ChapterTranscript({ bookId, chapterPosition }: Props) {
  const { currentSegment, voiceHues, seek, isPlaying } = usePlayer();
  const [segments, setSegments] = useState<SegmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
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
      <div className="mt-6 animate-pulse rounded-card border border-border bg-surface p-4 text-sm text-muted">
        Chargement de la transcription…
      </div>
    );
  }

  if (segments.length === 0) {
    return (
      <div className="mt-6 rounded-card border border-border bg-surface p-4 text-sm text-muted">
        Aucun segment disponible pour ce chapitre.
      </div>
    );
  }

  return (
    <div className="mt-6 overflow-hidden rounded-card border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="text-sm font-medium">📖 Transcription — Chapitre {chapterPosition}</p>
        {!hasTiming && (
          <p className="text-xs text-warning">
            ⚠️ Synchronisation indisponible — regénérez ce chapitre
          </p>
        )}
      </div>

      <div ref={setScrollRoot} className="max-h-[50vh] overflow-y-auto">
        {segments.map((seg) => {
          const isCurrent = currentSegment?.id === seg.id;
          const voiceId = seg.voice_id;
          const hue = voiceId ? (voiceHues.get(voiceId) ?? 0) : null;
          const label = seg.character_name ?? "Narrateur";
          const canSeek = seg.audio_offset_ms !== null;

          function seekToSegment() {
            if (seg.audio_offset_ms !== null) seek(seg.audio_offset_ms / 1000);
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
              aria-label={canSeek ? `Aller à ce passage — ${label}` : undefined}
              className={`flex gap-3 border-b border-border/50 px-4 py-2.5 transition-colors last:border-0 ${
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
            </div>
          );
        })}
      </div>
    </div>
  );
}
