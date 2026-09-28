"use client";

import type { BookSummary, ChapterSummary } from "@/lib/api";
import { formatClock } from "@/lib/resume";
import Button from "@/components/ui/Button";
import { AcxBadge, ExcerptButton } from "@/components/book/ChapterTools";
import StatusBadge from "@/components/ui/StatusBadge";
import { useT } from "@/lib/i18n/LanguageContext";

// Liste des chapitres : durée, inclusion (pages non narratives), génération et écoute.
// La ligne entière est cliquable pour écouter un chapitre terminé (audit 2026-09-25, UX-5).
export default function ChapterList({
  book,
  chapters,
  generatingPos,
  onGenerate,
  onToggleIncluded,
  onListen,
}: {
  book: BookSummary;
  chapters: ChapterSummary[];
  generatingPos: number | null;
  onGenerate: (position: number) => void;
  onToggleIncluded: (position: number, included: boolean) => void;
  onListen: (chapter: ChapterSummary) => void;
}) {
  const t = useT();
  // Génération par chapitre : possible dès que l'analyse est terminée (livre analysé, terminé
  // ou en échec) — pas pendant qu'il est en cours de traitement.
  const canGenerate = book.status === "ANALYZED" || book.status === "DONE" || book.status === "FAILED";

  return (
    <ul className="space-y-2.5">
      {chapters.map((ch) => {
        const listenable = ch.status === "DONE" && ch.included;
        return (
          <li
            key={ch.id}
            className={`flex items-center gap-3 rounded-2xl bg-surface-2/60 p-3.5 transition-colors hover:bg-surface-2 ${
              ch.included ? "" : "opacity-60"
            }`}
          >
            <input
              type="checkbox"
              checked={ch.included}
              disabled={ch.status === "GENERATING"}
              onChange={(e) => onToggleIncluded(ch.position, e.target.checked)}
              aria-label={ch.included ? t.flow.excludeChapter : t.flow.includeChapter}
              title={ch.included ? t.flow.excludeChapter : t.flow.includeChapter}
              className="h-4 w-4 shrink-0 cursor-pointer accent-primary"
            />
            <span className="w-7 text-right text-xs text-muted">{ch.position}</span>
            <button
              onClick={() => listenable && onListen(ch)}
              disabled={!listenable}
              className="min-w-0 flex-1 text-left disabled:cursor-default"
            >
              <p className="truncate text-sm">{ch.title ?? t.book.chapterFallback(ch.position)}</p>
              {ch.status === "FAILED" && ch.error_message && (
                <p className="text-xs text-danger">{ch.error_message}</p>
              )}
            </button>
            {ch.duration_ms !== null && ch.status === "DONE" && (
              <span className="hidden font-mono text-xs tabular-nums text-muted sm:inline">
                {formatClock(ch.duration_ms / 1000)}
              </span>
            )}
            {ch.included ? (
              <StatusBadge status={ch.status} className="text-xs" />
            ) : (
              <span className="text-xs text-muted">{t.flow.chapterExcluded}</span>
            )}
            {ch.included && canGenerate && ch.status !== "DONE" && ch.status !== "GENERATING" && (
              <ExcerptButton bookId={book.id} position={ch.position} />
            )}
            {ch.included && canGenerate && ch.status !== "DONE" && (
              <Button
                size="sm"
                onClick={() => onGenerate(ch.position)}
                disabled={generatingPos === ch.position || ch.status === "GENERATING"}
              >
                {generatingPos === ch.position ? "…" : t.book.generateChapter}
              </Button>
            )}
            {listenable && (
              <>
                <AcxBadge bookId={book.id} position={ch.position} />
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => onListen(ch)}
                  className="inline-flex items-center gap-1"
                >
                  <svg viewBox="0 0 16 16" fill="currentColor" className="ml-0.5 h-3 w-3 shrink-0">
                    <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
                  </svg>
                  {t.book.listen}
                </Button>
                {canGenerate && (
                  <Button
                    size="sm"
                    onClick={() => onGenerate(ch.position)}
                    disabled={generatingPos === ch.position}
                    title={t.book.regenerateChapter}
                    aria-label={t.book.regenerateChapter}
                  >
                    {generatingPos === ch.position ? "…" : "↺"}
                  </Button>
                )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
