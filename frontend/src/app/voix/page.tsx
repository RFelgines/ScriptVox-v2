"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  Gender,
  VoiceSummary,
  createVoice,
  deleteVoice,
  listVoices,
  patchVoiceFavorite,
  voiceSampleUrl,
} from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";

function localeToFlag(locale: string): string | null {
  const region = locale.split("-")[1];
  if (!region || region.length !== 2) return null;
  const codePoints = [...region.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65);
  return String.fromCodePoint(...codePoints);
}

const GENDER_SYMBOL: Partial<Record<Gender, string>> = {
  MALE: "♂",
  FEMALE: "♀",
};

// Angle d'or (137.5077...°) : assigner la N-ième teinte = N x angle d'or
// répartit n'importe quel nombre de couleurs sur le cercle chromatique de
// façon maximalement distincte.
const GOLDEN_ANGLE = 137.5077;

function buildOrbHueMap(voices: VoiceSummary[]): Map<string, number> {
  const sortedIds = voices.map((v) => v.id).sort();
  const map = new Map<string, number>();
  sortedIds.forEach((id, i) => map.set(id, (i * GOLDEN_ANGLE) % 360));
  return map;
}

function orbStyle(hue: number): CSSProperties {
  return {
    "--orb-c1": `hsl(${hue} 91% 65%)`,
    "--orb-c2": `hsl(${(hue + 59) % 360} 81% 60%)`,
    "--orb-c3": `hsl(${(hue + 347) % 360} 90% 66%)`,
  } as CSSProperties;
}

export default function VoixPage() {
  const { play } = usePlayer();
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  // ── Formulaire de clonage ──────────────────────────────────────────────────
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [cloneGender, setCloneGender] = useState<Gender | "">("");
  const [cloneFile, setCloneFile] = useState<File | null>(null);
  const [cloning, setCloning] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  function handleDeleteVoice(voice: VoiceSummary) {
    if (!window.confirm(`Supprimer la voix « ${voice.name} » ? Cette action est irréversible.`))
      return;
    setDeletingId(voice.id);
    deleteVoice(voice.id)
      .then(() => setVoices((prev) => prev.filter((v) => v.id !== voice.id)))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setDeletingId(null));
  }

  async function handleCloneSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!cloneName.trim()) { setCloneError("Le nom est requis."); return; }
    if (!cloneFile) { setCloneError("Un fichier audio de référence est requis."); return; }
    setCloneError(null);
    setCloning(true);
    try {
      const created = await createVoice(cloneName.trim(), (cloneGender as Gender) || null, cloneFile);
      setVoices((prev) => [...prev, created]);
      setCloneOpen(false);
      setCloneName("");
      setCloneGender("");
      setCloneFile(null);
    } catch (err) {
      setCloneError(err instanceof Error ? err.message : String(err));
    } finally {
      setCloning(false);
    }
  }

  const visible = favoritesOnly ? voices.filter((v) => v.is_favorite) : voices;
  // Calculé sur le catalogue complet (pas `visible`) : la couleur d'une voix
  // ne doit pas changer selon que le filtre "Favoris" est actif ou non.
  const orbHues = buildOrbHueMap(voices);

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold">Voix</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFavoritesOnly((v) => !v)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              favoritesOnly
                ? "bg-surface-2 text-foreground"
                : "text-muted hover:bg-surface-2/60 hover:text-foreground"
            }`}
          >
            ★ Favoris
          </button>
          <Button
            size="sm"
            onClick={() => {
              setCloneOpen((v) => !v);
              setCloneError(null);
            }}
          >
            {cloneOpen ? "✕ Annuler" : "+ Cloner une voix"}
          </Button>
        </div>
      </div>
      <p className="mt-2 text-muted">
        Le catalogue de voix disponibles. Cliquez sur un cercle pour écouter un aperçu.
      </p>

      {cloneOpen && (
        <form
          onSubmit={handleCloneSubmit}
          className="mt-6 rounded border border-border bg-surface p-4"
        >
          <h2 className="mb-4 text-base font-semibold">Cloner une voix</h2>
          <div className="flex flex-wrap gap-4">
            <label className="flex min-w-48 flex-1 flex-col gap-1 text-sm">
              Nom *
              <input
                type="text"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
                placeholder="ex. Patrick Baud"
                className="rounded border border-border bg-surface-2 px-3 py-1.5 text-sm placeholder:text-muted"
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Genre
              <select
                value={cloneGender}
                onChange={(e) => setCloneGender(e.target.value as Gender | "")}
                className="rounded border border-border bg-surface-2 px-3 py-1.5 text-sm"
              >
                <option value="">— Non précisé —</option>
                <option value="MALE">Masculin</option>
                <option value="FEMALE">Féminin</option>
                <option value="NEUTRAL">Neutre</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Audio de référence * (MP3 / WAV / FLAC)
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="rounded border border-dashed border-border bg-surface-2 px-4 py-1.5 text-sm text-muted hover:border-muted hover:text-foreground"
              >
                {cloneFile ? cloneFile.name : "Choisir un fichier…"}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".mp3,.wav,.flac"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setCloneFile(f);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          {cloneError && <p className="mt-3 text-sm text-red-400">{cloneError}</p>}
          <div className="mt-4 flex justify-end">
            <Button type="submit" variant="primary" disabled={cloning}>
              {cloning ? "Création en cours…" : "Créer la voix clonée"}
            </Button>
          </div>
        </form>
      )}

      {loading && <p className="mt-6 text-muted">Chargement…</p>}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-400">{error}</p>
        </Alert>
      )}

      {!loading && !error && visible.length === 0 && (
        <p className="mt-6 text-muted">
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
                  style={orbStyle(orbHues.get(v.id) ?? 0)}
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
                  className={`absolute -top-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full bg-surface text-sm shadow disabled:opacity-50 ${
                    v.is_favorite ? "text-amber-400" : "text-muted hover:text-foreground"
                  }`}
                >
                  {v.is_favorite ? "★" : "☆"}
                </button>
                {v.kind === "CLONED" && (
                  <button
                    onClick={() => handleDeleteVoice(v)}
                    disabled={deletingId === v.id}
                    aria-label={`Supprimer la voix ${v.name}`}
                    title="Supprimer cette voix clonée"
                    className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-surface text-xs text-muted shadow hover:bg-red-900/60 hover:text-red-300 disabled:opacity-50"
                  >
                    {deletingId === v.id ? "…" : "×"}
                  </button>
                )}
              </div>
              <p className="truncate text-sm font-medium" title={v.name}>
                {v.name}
              </p>
              <div className="flex flex-wrap items-center justify-center gap-1">
                {v.kind === "CLONED" && (
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">
                    🎙 cloné
                  </span>
                )}
                {v.locale && (
                  <span className="flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">
                    {localeToFlag(v.locale) ?? ""} {v.locale.split("-")[1] ?? v.locale}
                  </span>
                )}
                {v.gender && GENDER_SYMBOL[v.gender] && (
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-surface-2 text-xs text-muted">
                    {GENDER_SYMBOL[v.gender]}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
