"use client";

import type { CharacterSummary, VoiceSummary } from "@/lib/api";
import Select from "@/components/ui/Select";
import VoiceOrb from "@/components/VoiceOrb";
import VoiceDesign from "@/components/book/VoiceDesign";
import { useT } from "@/lib/i18n/LanguageContext";

// Ligne de casting : la voix choisie est ENREGISTRÉE immédiatement (avant : état « en attente »
// + coche de confirmation). L'aperçu se joue sur une réplique du personnage lui-même.
export default function CharacterRow({
  character: c,
  assignable,
  voiceMap,
  voiceHues,
  effectiveProvider,
  saving,
  previewing,
  onVoiceChange,
  onPreview,
  onDesigned,
}: {
  character: CharacterSummary;
  assignable: VoiceSummary[];
  voiceMap: Map<string, VoiceSummary>;
  voiceHues: Map<string, number>;
  effectiveProvider: string;
  saving: boolean;
  previewing: boolean;
  onVoiceChange: (characterId: number, voiceId: string) => void;
  onPreview: (character: CharacterSummary) => void;
  onDesigned?: () => void;
}) {
  const t = useT();
  const current = c.voice_id ? voiceMap.get(c.voice_id) : undefined;
  const incompatible =
    current !== undefined && current.kind === "CLONED" &&
    effectiveProvider !== "qwen" && effectiveProvider !== "omnivoice";

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-2xl bg-surface-2/60 p-3.5 transition-colors hover:bg-surface-2">
      <div className="min-w-40 flex-1">
        <p className="font-medium">{c.name}</p>
        <p className="text-xs text-muted">
          {c.gender}
          {c.age_category && c.age_category !== "UNKNOWN" ? ` · ${c.age_category}` : ""}
          {c.segment_count > 0 ? ` · ${t.book.segmentCount(c.segment_count)}` : ""}
        </p>
        {c.description && <p className="mt-1 line-clamp-2 text-xs text-muted">{c.description}</p>}
      </div>
      <div className="flex items-center gap-2">
        {incompatible && (
          <span title={t.book.clonedVoiceIncompatible(effectiveProvider)} className="text-warning">
            <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4" aria-hidden="true">
              <path
                d="M8 1.5L1 14h14L8 1.5zM8 6v4M8 11.5v1"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                fill="none"
              />
            </svg>
          </span>
        )}
        {current?.kind === "CLONED" && (
          <span className="whitespace-nowrap rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">
            {t.book.clonedBadge}
          </span>
        )}
        {c.voice_id ? (
          <VoiceOrb hue={voiceHues.get(c.voice_id) ?? 0} size={22} />
        ) : (
          <span className="h-[22px] w-[22px] shrink-0 rounded-full bg-surface-2" aria-hidden="true" />
        )}
        <Select
          value={c.voice_id ?? ""}
          disabled={saving}
          placeholder={t.book.chooseVoice}
          onChange={(v) => onVoiceChange(c.id, v)}
          options={[
            ...assignable
              .filter((v) => v.kind === "CATALOGUE")
              .map((v) => ({ value: v.id, label: `${v.name}${v.gender ? ` — ${v.gender}` : ""}` })),
            ...assignable
              .filter((v) => v.kind === "CLONED")
              .map((v) => ({
                value: v.id,
                label: `${v.name}${v.gender ? ` — ${v.gender}` : ""}`,
                group: t.book.clonedVoicesGroup,
              })),
          ]}
        />
        {c.voice_id && (
          <button
            onClick={() => onPreview(c)}
            disabled={previewing}
            title={previewing ? t.flow.previewLoading : t.flow.previewOnLine}
            aria-label={t.flow.previewOnLine}
            className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-foreground disabled:opacity-50"
          >
            {previewing ? (
              <span className="text-xs">…</span>
            ) : (
              <svg viewBox="0 0 16 16" fill="currentColor" className="ml-0.5 h-3.5 w-3.5">
                <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
              </svg>
            )}
          </button>
        )}
        {saving && <span className="text-xs text-muted">…</span>}
      </div>
      {onDesigned && <VoiceDesign characterId={c.id} onDesigned={onDesigned} />}
    </li>
  );
}
