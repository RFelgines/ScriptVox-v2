"use client";

import { useEffect, useState } from "react";
import { AppSettings, AppStatus, getAppSettings, getAppStatus, updateAppSettings } from "@/lib/api";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";
import { useT } from "@/lib/i18n/LanguageContext";
import type { Dictionary } from "@/lib/i18n/translations";

type StatusLevel = "ok" | "warning" | "error";

function StatusDot({ level }: { level: StatusLevel }) {
  const colors: Record<StatusLevel, string> = {
    ok: "bg-green-500",
    warning: "bg-amber-500",
    error: "bg-red-500",
  };
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${colors[level]}`}
      aria-hidden="true"
    />
  );
}

function ProviderCard({
  label,
  name,
  status,
  detail,
  t,
}: {
  label: string;
  name: string;
  status: StatusLevel;
  detail: string | null;
  t: Dictionary;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-2 flex items-center gap-2">
        <StatusDot level={status} />
        <p className="font-medium text-foreground">{name}</p>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-xs text-muted">{t.settings.statusLevels[status]}</span>
        {detail && <span className="text-xs text-muted">— {detail}</span>}
      </div>
    </div>
  );
}

function PrivacyBadge({ llmProvider, t }: { llmProvider: string; t: Dictionary }) {
  const isCloud = llmProvider === "gemini";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isCloud
          ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
          : "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
      }`}
    >
      {isCloud ? t.settings.privacyBadgeCloud : t.settings.privacyBadgeLocal}
    </span>
  );
}

export default function ParametresPage() {
  const t = useT();
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);

  useEffect(() => {
    Promise.all([getAppStatus(), getAppSettings()])
      .then(([s, cfg]) => {
        setStatus(s);
        setSettings(cfg);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  function handlePreferredLlmChange(value: string) {
    if (!settings) return;
    const preferred = value === "" ? null : value;
    setSettings({ ...settings, preferred_llm_provider: preferred });
    setSaving(true);
    updateAppSettings({ preferred_llm_provider: preferred })
      .then(setSettings)
      .catch((e) => setError(String(e)))
      .finally(() => setSaving(false));
  }

  function handlePreferredProviderChange(value: string) {
    if (!settings) return;
    const preferred = value === "" ? null : value;
    setSettings({ ...settings, preferred_tts_provider: preferred });
    setSaving(true);
    updateAppSettings({ preferred_tts_provider: preferred })
      .then(setSettings)
      .catch((e) => setError(String(e)))
      .finally(() => setSaving(false));
  }

  function handleTestConnection() {
    setTestingConnection(true);
    getAppStatus()
      .then(setStatus)
      .catch((e) => setError(String(e)))
      .finally(() => setTestingConnection(false));
  }

  const effectiveLlm = settings
    ? (settings.preferred_llm_provider ?? settings.default_llm_provider)
    : null;

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-3xl font-bold text-foreground">{t.settings.title}</h1>
      <p className="mt-2 text-muted">
        {t.settings.subtitle}
      </p>

      {loading && (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-24 rounded-card" />
          <Skeleton className="h-24 rounded-card" />
          <Skeleton className="h-10 rounded-card" />
        </div>
      )}

      {error && (
        <Alert title={t.settings.apiUnreachableTitle} className="mt-6">
          <p className="text-sm text-danger">{error}</p>
        </Alert>
      )}

      {settings && (
        <div className="mt-6 space-y-3">
          {/* Sélecteur LLM + badge confidentialité */}
          <div className="rounded-card border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              {t.settings.preferredLlmLabel}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select
                value={settings.preferred_llm_provider ?? ""}
                onChange={(e) => handlePreferredLlmChange(e.target.value)}
                disabled={saving}
                className="rounded-control border border-border bg-surface-2 px-2 py-1.5 text-sm text-foreground disabled:opacity-50"
                aria-label={t.settings.preferredLlmLabel}
              >
                <option value="">{t.settings.defaultOption(settings.default_llm_provider)}</option>
                {settings.available_llm_providers.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              {effectiveLlm && <PrivacyBadge llmProvider={effectiveLlm} t={t} />}
              {saving && <span className="text-xs text-muted">{t.settings.saving}</span>}
            </div>
            <p className="mt-2 text-xs text-muted">{t.settings.preferredLlmHint}</p>
          </div>

          {/* Sélecteur TTS */}
          <div className="rounded-card border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              {t.settings.preferredProviderLabel}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <select
                value={settings.preferred_tts_provider ?? ""}
                onChange={(e) => handlePreferredProviderChange(e.target.value)}
                disabled={saving}
                className="rounded-control border border-border bg-surface-2 px-2 py-1.5 text-sm text-foreground disabled:opacity-50"
                aria-label={t.settings.preferredProviderLabel}
              >
                <option value="">{t.settings.defaultOption(settings.default_tts_provider)}</option>
                {settings.available_tts_providers.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              {saving && <span className="text-xs text-muted">{t.settings.saving}</span>}
            </div>
            <p className="mt-2 text-xs text-muted">
              {t.settings.preferredHint}
            </p>
          </div>

          {/* Bouton "Tester la connexion" */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleTestConnection}
              disabled={testingConnection}
              className="rounded-control border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-foreground hover:bg-surface transition-colors disabled:opacity-50"
            >
              {testingConnection ? t.settings.testConnectionTesting : t.settings.testConnection}
            </button>
          </div>
        </div>
      )}

      {status && (
        <div className="mt-3 space-y-3">
          <ProviderCard
            label={t.settings.llmLabel}
            name={status.llm.name}
            status={status.llm.status}
            detail={status.llm.detail}
            t={t}
          />
          <ProviderCard
            label={t.settings.ttsLabel}
            name={status.tts.name}
            status={status.tts.status}
            detail={status.tts.detail}
            t={t}
          />

          <div className="rounded-card border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              {t.settings.clonedVoicesLabel}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot level={status.cloned_voices_count > 0 ? "ok" : "warning"} />
              <p className="font-medium text-foreground">
                {status.cloned_voices_count > 0
                  ? t.settings.clonedVoicesAvailable(status.cloned_voices_count)
                  : t.settings.clonedVoicesNone}
              </p>
            </div>
            <p className="mt-1 text-xs text-muted">
              {status.cloned_voices_count > 0
                ? t.settings.clonedVoicesHintAvailable
                : t.settings.clonedVoicesHintNone}
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
