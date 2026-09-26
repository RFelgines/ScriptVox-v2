"use client";

import type { BookSummary, ChapterSummary } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";
import type { Dictionary } from "@/lib/i18n/translations";

function formatEta(seconds: number, t: Dictionary): string {
  if (seconds < 60) return t.flow.etaLessThanMinute;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return t.flow.etaMinutes(minutes);
  return t.flow.etaHours(Math.floor(minutes / 60), minutes % 60);
}

// Étape en cours, chapitre X/Y, temps restant et barre d'avancement DANS l'étape
// (audit 2026-09-25, BE-5 / UX-2) — avant : une seule barre globale qui sautait de 0 à 60 %.
export default function BookProgress({
  book,
  chapters,
}: {
  book: BookSummary;
  chapters: ChapterSummary[];
}) {
  const t = useT();
  const running = book.status === "PROCESSING" || book.status === "GENERATING";
  if (!running) return null;

  const stage = book.stage ?? (book.status === "PROCESSING" ? "analysis" : "generation");
  const stageLabel =
    stage === "analysis"
      ? t.flow.stageAnalysis
      : stage === "assembly"
        ? t.flow.stageAssembly
        : t.flow.stageGeneration;

  const included = chapters.filter((c) => c.included);
  const total = included.length;
  let current = 0;
  if (stage === "generation") {
    const done = included.filter((c) => c.status === "DONE").length;
    const busy = included.some((c) => c.status === "GENERATING") ? 1 : 0;
    current = Math.min(total, done + busy);
  } else if (stage === "analysis") {
    current = Math.min(total, Math.max(1, Math.round((book.stage_progress / 100) * total)));
  }

  const parts: string[] = [stageLabel];
  if (total > 0 && stage !== "assembly") parts.push(t.flow.chapterProgress(current, total));
  if (book.eta_seconds !== null && book.eta_seconds !== undefined) {
    parts.push(formatEta(book.eta_seconds, t));
  }
  const pct = Math.max(2, Math.min(100, book.stage_progress > 0 ? book.stage_progress : book.progress));

  return (
    <div className="mt-3 w-full max-w-md">
      <p className="text-sm text-muted">{parts.join(" · ")}</p>
      <div
        className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
