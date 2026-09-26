"use client";

import { useEffect, useId, useState } from "react";
import {
  AppSettings,
  EngineOptions,
  listModels,
  updateAppSettings,
  type SettingsPatch,
} from "@/lib/api";
import { useFeedback } from "@/components/ui/Feedback";
import { useT } from "@/lib/i18n/LanguageContext";

type Kind = "llm" | "tts";
type Field = "model" | "base_url" | "base_model" | "locale";

// Champs éditables selon le moteur. Un moteur inconnu (plugin) expose au moins « model ».
function fieldsFor(kind: Kind, provider: string): Field[] {
  if (kind === "llm") {
    if (provider === "ollama" || provider === "openai_compatible") return ["model", "base_url"];
    return ["model"];
  }
  if (provider === "qwen") return ["model", "base_model"];
  if (provider === "edgetts") return ["locale"];
  if (provider === "openai_tts") return ["model", "base_url"];
  if (provider === "piper" || provider === "command") return [];
  return ["model"];
}

// Exemple d'adresse adapté au moteur choisi (affiché en filigrane quand le champ est vide).
function baseUrlExample(provider: string): string {
  if (provider === "ollama") return "http://localhost:11434";
  if (provider === "openai_compatible") return "http://localhost:1234/v1";
  if (provider === "openai_tts") return "http://localhost:8880/v1";
  return "http://localhost:8000";
}

// Un moteur dont le texte du livre quitte la machine (badge « cloud »).
function isCloud(kind: Kind, provider: string): boolean {
  return kind === "llm" ? provider === "gemini" : provider === "edgetts";
}

export default function EngineSettings({
  kind,
  settings,
  onChange,
}: {
  kind: Kind;
  settings: AppSettings;
  onChange: (next: AppSettings) => void;
}) {
  const t = useT();
  const { toast } = useFeedback();
  const listId = useId();

  const defaultProvider = kind === "llm" ? settings.default_llm_provider : settings.default_tts_provider;
  const preferred = kind === "llm" ? settings.preferred_llm_provider : settings.preferred_tts_provider;
  const providers = kind === "llm" ? settings.available_llm_providers : settings.available_tts_providers;
  const descriptions =
    kind === "llm" ? settings.llm_provider_descriptions : settings.tts_provider_descriptions;
  const saved: EngineOptions = kind === "llm" ? settings.llm_options : settings.tts_options;
  const effectiveModel = kind === "llm" ? settings.effective_llm_model : settings.effective_tts_model;

  const [provider, setProvider] = useState(preferred ?? "");
  const [draft, setDraft] = useState<EngineOptions>(saved);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [saving, setSaving] = useState(false);

  const activeProvider = provider || defaultProvider;
  const fields = fieldsFor(kind, activeProvider);

  // Suggestions de modèles du moteur choisi (installés localement quand il sait les lister).
  useEffect(() => {
    let active = true;
    listModels(kind, activeProvider)
      .then((res) => {
        if (!active) return;
        setSuggestions(res.models);
        setListError(res.error);
      })
      .catch((e) => {
        if (!active) return;
        setSuggestions([]);
        setListError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      active = false;
    };
  }, [kind, activeProvider, refreshNonce]);

  function setField(field: Field, value: string) {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }

  async function save() {
    setSaving(true);
    // Seuls les champs affichés pour ce moteur sont envoyés ; « vide » = pas de surcharge.
    const options: EngineOptions = {};
    for (const f of fields) options[f] = (draft[f] ?? "").trim();
    const patch: SettingsPatch =
      kind === "llm"
        ? { preferred_llm_provider: provider || null, llm_options: options }
        : { preferred_tts_provider: provider || null, tts_options: options };
    try {
      onChange(await updateAppSettings(patch));
      toast(t.models.savedToast);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), { tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  const inputClass =
    "w-full rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted/60";
  const labelClass = "text-xs font-medium text-muted";

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          {kind === "llm" ? t.models.llmTitle : t.models.ttsTitle}
        </p>
        {isCloud(kind, activeProvider) && (
          <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
            {kind === "llm" ? t.flow.privacyCloudLlm : t.flow.privacyCloudTts}
          </span>
        )}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={labelClass}>{t.models.providerLabel}</span>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            disabled={saving}
            className="rounded-control border border-border bg-surface-2 px-2 py-1.5 text-sm text-foreground disabled:opacity-50"
          >
            <option value="">{t.settings.defaultOption(defaultProvider)}</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          {descriptions[activeProvider] && (
            <span className="text-xs text-muted">{descriptions[activeProvider]}</span>
          )}
        </label>

        {fields.includes("model") && (
          <label className="flex flex-col gap-1">
            <span className={labelClass}>{t.models.modelLabel}</span>
            <input
              list={listId}
              value={draft.model ?? ""}
              onChange={(e) => setField("model", e.target.value)}
              placeholder={effectiveModel ?? t.models.modelPlaceholder}
              className={inputClass}
              spellCheck={false}
              autoComplete="off"
            />
            <datalist id={listId}>
              {suggestions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <span className="text-xs text-muted">{t.models.modelHint}</span>
          </label>
        )}

        {fields.includes("base_model") && (
          <label className="flex flex-col gap-1">
            <span className={labelClass}>{t.models.baseModelLabel}</span>
            <input
              value={draft.base_model ?? ""}
              onChange={(e) => setField("base_model", e.target.value)}
              placeholder="Qwen/Qwen3-TTS-12Hz-1.7B-Base"
              className={inputClass}
              spellCheck={false}
              autoComplete="off"
            />
          </label>
        )}

        {fields.includes("base_url") && (
          <label className="flex flex-col gap-1">
            <span className={labelClass}>{t.models.baseUrlLabel}</span>
            <input
              value={draft.base_url ?? ""}
              onChange={(e) => setField("base_url", e.target.value)}
              placeholder={baseUrlExample(activeProvider)}
              className={inputClass}
              spellCheck={false}
              autoComplete="off"
            />
            <span className="text-xs text-muted">{t.models.baseUrlHint}</span>
          </label>
        )}

        {fields.includes("locale") && (
          <label className="flex flex-col gap-1">
            <span className={labelClass}>{t.models.localeLabel}</span>
            <input
              list={listId}
              value={draft.locale ?? ""}
              onChange={(e) => setField("locale", e.target.value)}
              placeholder="fr-FR"
              className={inputClass}
              spellCheck={false}
              autoComplete="off"
            />
            <datalist id={listId}>
              {suggestions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-control bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {saving ? t.models.savingButton : t.models.saveButton}
        </button>
        {fields.includes("model") && (
          <button
            onClick={() => setRefreshNonce((n) => n + 1)}
            className="text-xs text-muted underline underline-offset-2 hover:text-foreground"
          >
            {t.models.refreshList}
          </button>
        )}
        {effectiveModel && <span className="text-xs text-muted">{t.models.effectiveModel(effectiveModel)}</span>}
      </div>
      {listError && fields.includes("model") && (
        <p className="mt-2 text-xs text-muted">{t.models.listError(listError)}</p>
      )}
    </div>
  );
}
