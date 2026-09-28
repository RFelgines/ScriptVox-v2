"use client";

import { useEffect, useRef, useState } from "react";
import {
  chapterExcerptReady,
  chapterExcerptUrl,
  getChapterLoudness,
  requestChapterExcerpt,
  type LoudnessReport,
} from "@/lib/api";
import Button from "@/components/ui/Button";
import { useT } from "@/lib/i18n/LanguageContext";

// Extrait (~1 min) d'un chapitre avant rendu : lancé côté worker (tâche prioritaire), puis
// réinterrogé jusqu'à ce que le WAV existe, et joué ici.
export function ExcerptButton({ bookId, position }: { bookId: number; position: number }) {
  const t = useT();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const cancelled = useRef(false);

  useEffect(() => () => {
    cancelled.current = true;
    audio.current?.pause();
  }, []);

  async function play() {
    setError(null);
    setLoading(true);
    try {
      let { ready } = await requestChapterExcerpt(bookId, position);
      for (let i = 0; !ready && i < 120 && !cancelled.current; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        ready = await chapterExcerptReady(bookId, position);
      }
      if (!ready || cancelled.current) return;
      audio.current?.pause();
      audio.current = new Audio(`${chapterExcerptUrl(bookId, position)}?t=${Date.now()}`);
      await audio.current.play();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button size="sm" onClick={play} disabled={loading} title={error ?? t.production.excerptTitle}>
      {loading ? t.production.excerptLoading : `▸ ${t.production.excerpt}`}
    </Button>
  );
}

// Contrôle ACX d'un chapitre terminé : mesuré à la demande (lecture du WAV côté API).
export function AcxBadge({ bookId, position }: { bookId: number; position: number }) {
  const t = useT();
  const [report, setReport] = useState<LoudnessReport | null>(null);
  const [loading, setLoading] = useState(false);

  async function check() {
    setLoading(true);
    try {
      setReport(await getChapterLoudness(bookId, position));
    } catch {
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  if (!report) {
    return (
      <button
        onClick={check}
        disabled={loading}
        className="rounded-full px-2 py-0.5 text-xs text-muted hover:bg-surface-2 hover:text-foreground"
      >
        {loading ? "…" : t.production.acxCheck}
      </button>
    );
  }
  const ok = report.acx_compliant;
  return (
    <span
      title={t.production.acxTitle(String(report.rms_dbfs ?? "-∞"), String(report.peak_dbfs ?? "-∞"))}
      className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${
        ok ? "bg-success/15 text-success" : "bg-warning/15 text-warning"
      }`}
    >
      {ok ? `✓ ${t.production.acxOk}` : `! ${t.production.acxKo}`}
    </span>
  );
}
