"use client";

import { useEffect, useState } from "react";
import { AppSettings, AppStatus, getAppSettings, getAppStatus, updateAppSettings } from "@/lib/api";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";

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
}: {
  label: string;
  name: string;
  status: StatusLevel;
  detail: string | null;
}) {
  const labels: Record<StatusLevel, string> = {
    ok: "Opérationnel",
    warning: "Attention",
    error: "Erreur",
  };
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-2 flex items-center gap-2">
        <StatusDot level={status} />
        <p className="font-medium text-foreground">{name}</p>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-xs text-muted">{labels[status]}</span>
        {detail && <span className="text-xs text-muted">— {detail}</span>}
      </div>
    </div>
  );
}

export default function ParametresPage() {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

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

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-bold text-foreground">Paramètres</h1>
      <p className="mt-2 text-muted">
        État des services. Le moteur de synthèse par livre se choisit dans la page Casting.
      </p>

      {loading && (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-24 rounded-card" />
          <Skeleton className="h-24 rounded-card" />
          <Skeleton className="h-10 rounded-card" />
        </div>
      )}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-500">{error}</p>
        </Alert>
      )}

      {status && (
        <div className="mt-6 space-y-3">
          <ProviderCard
            label="Analyse LLM"
            name={status.llm.name}
            status={status.llm.status}
            detail={status.llm.detail}
          />
          <ProviderCard
            label="Synthèse vocale TTS"
            name={status.tts.name}
            status={status.tts.status}
            detail={status.tts.detail}
          />

          {settings && (
            <div className="rounded-card border border-border bg-surface p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Modèle TTS préféré
              </p>
              <div className="mt-2 flex items-center gap-2">
                <select
                  value={settings.preferred_tts_provider ?? ""}
                  onChange={(e) => handlePreferredProviderChange(e.target.value)}
                  disabled={saving}
                  className="rounded-control border border-border bg-surface-2 px-2 py-1.5 text-sm text-foreground disabled:opacity-60"
                  aria-label="Modèle TTS préféré"
                >
                  <option value="">Par défaut ({settings.default_tts_provider})</option>
                  {settings.available_tts_providers.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                {saving && <span className="text-xs text-muted">Enregistrement…</span>}
              </div>
              <p className="mt-2 text-xs text-muted">
                Préférence enregistrée, pas encore appliquée à la génération — le moteur réel reste
                celui choisi par livre (page Casting) ou la valeur par défaut du serveur.
              </p>
            </div>
          )}

          <div className="rounded-card border border-border bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              Voix clonées
            </p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot level={status.cloned_voices_count > 0 ? "ok" : "warning"} />
              <p className="font-medium text-foreground">
                {status.cloned_voices_count > 0
                  ? `${status.cloned_voices_count} voix clonée${status.cloned_voices_count > 1 ? "s" : ""} disponible${status.cloned_voices_count > 1 ? "s" : ""}`
                  : "Aucune voix clonée"}
              </p>
            </div>
            <p className="mt-1 text-xs text-muted">
              {status.cloned_voices_count > 0
                ? "Utilisables avec Qwen3-TTS uniquement — assignées en priorité lors de l'analyse."
                : "Ajoutez des voix depuis l'onglet Voix pour activer le clonage."}
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
