"use client";

import { useEffect, useState } from "react";
import { AppSettings, getAppSettings } from "@/lib/api";
import Alert from "@/components/ui/Alert";

const PROVIDER_LABELS: Record<string, string> = {
  edgetts: "EdgeTTS — rapide, par défaut pour les livres complets",
  qwen: "Qwen3-TTS — émotion/clonage, plus lent (prévisu)",
  elevenlabs: "ElevenLabs",
  piper: "Piper — local, hors-ligne",
};

export default function ParametresPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAppSettings()
      .then((s) => {
        setSettings(s);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-bold text-foreground">Paramètres</h1>
      <p className="mt-2 text-muted">
        Réglages globaux de l&apos;application. Le choix du moteur de synthèse pour un
        livre donné se fait sur sa page de Casting.
      </p>

      {loading && <p className="mt-6 text-muted">Chargement…</p>}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-400">{error}</p>
        </Alert>
      )}

      {settings && (
        <div className="mt-6 rounded-card border border-border bg-surface p-4">
          <p className="text-sm text-muted">Moteur de synthèse par défaut</p>
          <p className="mt-1 font-medium">
            {PROVIDER_LABELS[settings.default_tts_provider] ?? settings.default_tts_provider}
          </p>

          <p className="mt-4 text-sm text-muted">Moteurs disponibles</p>
          <ul className="mt-1 space-y-1">
            {settings.available_tts_providers.map((p) => (
              <li key={p} className="text-sm">
                {PROVIDER_LABELS[p] ?? p}
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}
