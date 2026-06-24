"use client";

import { useEffect, useState } from "react";
import { VoiceSummary, listVoices, patchVoiceFavorite, voiceSampleUrl } from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import Alert from "@/components/ui/Alert";

export default function VoixPage() {
  const { play } = usePlayer();
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  useEffect(() => {
    listVoices()
      .then((data) => {
        setVoices(data);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  function toggleFavorite(voice: VoiceSummary) {
    setSavingId(voice.id);
    patchVoiceFavorite(voice.id, !voice.is_favorite)
      .then((updated) =>
        setVoices((prev) => prev.map((v) => (v.id === updated.id ? updated : v))),
      )
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingId(null));
  }

  const visible = favoritesOnly ? voices.filter((v) => v.is_favorite) : voices;

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold">Voix</h1>
        <button
          onClick={() => setFavoritesOnly((v) => !v)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            favoritesOnly
              ? "bg-gray-800 text-violet-400"
              : "text-gray-400 hover:bg-gray-800/60 hover:text-gray-100"
          }`}
        >
          ★ Favoris
        </button>
      </div>
      <p className="mt-2 text-gray-400">
        Le catalogue de voix disponibles. Cliquez sur un cercle pour écouter un aperçu.
      </p>

      {loading && <p className="mt-6 text-gray-500">Chargement…</p>}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-400">{error}</p>
        </Alert>
      )}

      {!loading && !error && visible.length === 0 && (
        <p className="mt-6 text-gray-500">
          {favoritesOnly ? "Aucune voix en favori pour l'instant." : "Aucune voix disponible."}
        </p>
      )}

      {visible.length > 0 && (
        <div className="mt-8 flex flex-wrap gap-x-6 gap-y-8">
          {visible.map((v) => (
            <div key={v.id} className="flex w-28 flex-col items-center gap-2">
              <div className="relative">
                <button
                  onClick={() => play({ title: `Aperçu — ${v.name}`, src: voiceSampleUrl(v.id) })}
                  aria-label={`Écouter un aperçu de ${v.name}`}
                  className="voice-orb group flex h-24 w-24 items-center justify-center rounded-full shadow-lg transition-transform hover:scale-105"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-black/30 text-white opacity-0 transition-opacity group-hover:opacity-100">
                    ▶
                  </span>
                </button>
                <button
                  onClick={() => toggleFavorite(v)}
                  disabled={savingId === v.id}
                  aria-label={v.is_favorite ? "Retirer des favoris" : "Ajouter aux favoris"}
                  className={`absolute -top-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full bg-gray-900 text-sm shadow disabled:opacity-50 ${
                    v.is_favorite ? "text-amber-400" : "text-gray-500 hover:text-gray-300"
                  }`}
                >
                  {v.is_favorite ? "★" : "☆"}
                </button>
              </div>
              <p className="truncate text-sm font-medium" title={v.name}>
                {v.name}
              </p>
              {v.gender && <p className="text-xs text-gray-500">{v.gender}</p>}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
