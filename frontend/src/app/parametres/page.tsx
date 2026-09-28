"use client";

import { useEffect, useState } from "react";
import {
  AppSettings,
  AppStatus,
  getAppSettings,
  getAppStatus,
  unloadModels,
  updateAppSettings,
} from "@/lib/api";
import EngineSettings from "@/components/EngineSettings";
import LexiconEditor from "@/components/LexiconEditor";
import { useFeedback } from "@/components/ui/Feedback";
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

export default function ParametresPage() {
  const t = useT();
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [testingConnection, setTestingConnection] = useState(false);
  const [engineKey, setEngineKey] = useState(0);
  const { toast } = useFeedback();

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

  // Profils rapides : bascule LLM + TTS d'un coup (les réglages fins restent éditables dessous).
  function applyPreset(preset: "local" | "cloud") {
    const patch =
      preset === "local"
        ? { preferred_llm_provider: "ollama", preferred_tts_provider: "qwen" }
        : { preferred_llm_provider: "gemini", preferred_tts_provider: "edgetts" };
    updateAppSettings(patch)
      .then((next) => {
        setSettings(next);
        setEngineKey((k) => k + 1); // remonte les éditeurs avec les nouvelles valeurs
        toast(t.models.savedToast);
      })
      .catch((e) => toast(e instanceof Error ? e.message : String(e), { tone: "error" }));
  }

  function handleFreeGpu() {
    unloadModels()
      .then(() => toast(t.models.freeGpuDone))
      .catch((e) => toast(e instanceof Error ? e.message : String(e), { tone: "error" }));
  }

  function handleTestConnection() {
    setTestingConnection(true);
    // deep : appels réels aux services distants (Gemini, serveur TTS…).
    getAppStatus(true)
      .then(setStatus)
      .catch((e) => setError(String(e)))
      .finally(() => setTestingConnection(false));
  }

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
          {/* Profils rapides */}
          <div className="rounded-card border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              {t.models.presetsTitle}
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <button
                onClick={() => applyPreset("local")}
                className="rounded-control border border-border bg-surface-2 px-3 py-2 text-left transition-colors hover:bg-surface-2/70"
              >
                <span className="block text-sm font-medium">{t.models.presetLocal}</span>
                <span className="block text-xs text-muted">{t.models.presetLocalNote}</span>
              </button>
              <button
                onClick={() => applyPreset("cloud")}
                className="rounded-control border border-border bg-surface-2 px-3 py-2 text-left transition-colors hover:bg-surface-2/70"
              >
                <span className="block text-sm font-medium">{t.models.presetCloud}</span>
                <span className="block text-xs text-muted">{t.models.presetCloudNote}</span>
              </button>
            </div>
          </div>

          <p className="px-1 pt-2 text-sm text-muted">{t.models.sectionHint}</p>
          <EngineSettings key={`llm-${engineKey}`} kind="llm" settings={settings} onChange={setSettings} />
          <EngineSettings key={`tts-${engineKey}`} kind="tts" settings={settings} onChange={setSettings} />
          <p className="px-1 text-xs text-muted">{t.settings.preferredHint}</p>

          <details className="rounded-2xl bg-surface-2/30 p-4">
            <summary className="cursor-pointer font-medium">{t.production.lexiconGlobalTitle}</summary>
            <div className="mt-3">
              <LexiconEditor />
            </div>
          </details>

          {settings.plugin_errors.length > 0 && (
            <Alert title={t.models.pluginErrorsTitle}>
              <ul className="mt-1 space-y-1 text-xs text-muted">
                {settings.plugin_errors.map((e) => (
                  <li key={e.file}>
                    <code className="rounded bg-surface-2 px-1">{e.file}</code> — {e.error}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">{t.models.pluginHint}</p>
            </Alert>
          )}

          {/* Bouton "Tester la connexion" */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleTestConnection}
              disabled={testingConnection}
              className="rounded-control border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-foreground hover:bg-surface transition-colors disabled:opacity-50"
            >
              {testingConnection ? t.settings.testConnectionTesting : t.settings.testConnection}
            </button>
            <button
              onClick={handleFreeGpu}
              className="rounded-control border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-foreground hover:bg-surface transition-colors"
            >
              {t.models.freeGpu}
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
