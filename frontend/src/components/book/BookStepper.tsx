"use client";

import type { BookStatus } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";

// Parcours en 4 étapes : Analyse -> Casting -> Génération -> Écoute (audit 2026-09-25, UX-1).
function currentStep(status: BookStatus, failedStage: "analysis" | "generation" | null): number {
  switch (status) {
    case "PENDING":
    case "PROCESSING":
      return 0;
    case "ANALYZED":
      return 1;
    case "GENERATING":
      return 2;
    case "DONE":
      return 3;
    case "FAILED":
      return failedStage === "generation" ? 2 : 0;
  }
}

export default function BookStepper({
  status,
  failedStage,
}: {
  status: BookStatus;
  failedStage: "analysis" | "generation" | null;
}) {
  const t = useT();
  const labels = [t.flow.stepAnalysis, t.flow.stepCasting, t.flow.stepGeneration, t.flow.stepListen];
  const current = currentStep(status, failedStage);
  const failed = status === "FAILED";

  return (
    <ol className="mt-6 flex items-center gap-1 text-xs sm:gap-2" aria-label="Progression">
      {labels.map((label, i) => {
        const done = i < current || (status === "DONE" && i === current);
        const active = i === current && !done;
        return (
          <li key={label} className="flex min-w-0 flex-1 items-center gap-2">
            <span
              aria-current={active ? "step" : undefined}
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold ${
                done
                  ? "border-primary bg-primary text-primary-foreground"
                  : active
                    ? failed
                      ? "border-danger text-danger"
                      : "border-primary text-foreground"
                    : "border-border text-muted"
              }`}
            >
              {done ? "✓" : i + 1}
            </span>
            <span
              className={`truncate ${active ? "font-medium text-foreground" : "text-muted"}`}
            >
              {label}
            </span>
            {i < labels.length - 1 && (
              <span
                aria-hidden="true"
                className={`h-px min-w-3 flex-1 ${i < current ? "bg-primary" : "bg-border"}`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
