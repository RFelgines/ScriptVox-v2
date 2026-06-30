"use client";

import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { SegmentSummary, getChapterSegments } from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";

function orbStyle(hue: number): CSSProperties {
  return {
    "--orb-c1": `hsl(${hue} 91% 65%)`,
    "--orb-c2": `hsl(${(hue + 59) % 360} 81% 60%)`,
    "--orb-c3": `hsl(${(hue + 347) % 360} 90% 66%)`,
  } as CSSProperties;
}

interface Props {
  bookId: number;
  chapterPosition: number;
}

export default function ChapterTranscript({ bookId, chapterPosition }: Props) {
  const { currentSegment, voiceHues } = usePlayer();
  const [segments, setSegments] = useState<SegmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const currentRef = useRef<HTMLDivElement | null>(null);

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
          <p className="text-xs text-amber-400">
            ⚠️ Synchronisation indisponible — regénérez ce chapitre
          </p>
        )}
      </div>

      <div className="max-h-[50vh] overflow-y-auto">
        {segments.map((seg) => {
          const isCurrent = currentSegment?.id === seg.id;
          const voiceId = seg.voice_id;
          const hue = voiceId ? (voiceHues.get(voiceId) ?? 0) : null;
          const label = seg.character_name ?? "Narrateur";

          return (
            <div
              key={seg.id}
              ref={isCurrent ? currentRef : null}
              className={`flex gap-3 border-b border-border/50 px-4 py-2.5 transition-colors last:border-0 ${
                isCurrent
                  ? "bg-primary/8 border-l-2 border-l-primary"
                  : "hover:bg-surface-2/40"
              }`}
            >
              {/* Indicateur de voix */}
              <div className="flex w-28 shrink-0 items-start gap-1.5 pt-0.5">
                {hue !== null ? (
                  <div
                    style={orbStyle(hue)}
                    className="voice-orb mt-0.5 h-4 w-4 shrink-0 rounded-full"
                    aria-hidden="true"
                  />
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
