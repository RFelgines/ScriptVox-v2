"use client";

import { useEffect, useState } from "react";
import { AppStatus, getAppStatus } from "@/lib/api";
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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAppStatus()
      .then((s) => {
        setStatus(s);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

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
