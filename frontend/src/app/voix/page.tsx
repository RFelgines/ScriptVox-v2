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
import Skeleton from "@/components/ui/Skeleton";
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
                className="rounded-control border border-border bg-surface-2 px-3 py-1.5 text-sm placeholder:text-muted"
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
                className="rounded-control border border-dashed border-border bg-surface-2 px-4 py-1.5 text-sm text-muted hover:border-muted hover:text-foreground"
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
          {cloneError && <p className="mt-3 text-sm text-red-500">{cloneError}</p>}
          <div className="mt-4 flex justify-end">
            <Button type="submit" variant="primary" disabled={cloning}>
              {cloning ? "Création en cours…" : "Créer la voix clonée"}
            </Button>
          </div>
        </form>
      )}

      {loading && (
        <div className="mt-8 flex flex-wrap gap-x-6 gap-y-8">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex w-28 flex-col items-center gap-2">
              <Skeleton className="h-24 w-24 rounded-full" />
              <Skeleton className="h-3 w-16 rounded" />
              <Skeleton className="h-5 w-10 rounded-full" />
            </div>
          ))}
        </div>
      )}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-500">{error}</p>
        </Alert>
      )}

      {!loading && !error && visible.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-3 text-center text-muted">
          {favoritesOnly ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          )}
          <p className="text-base font-medium text-foreground">
            {favoritesOnly ? "Aucun favori" : "Aucune voix disponible"}
          </p>
          <p className="text-sm">
            {favoritesOnly
              ? "Cliquez l'étoile sur une voix pour la mettre en favori."
              : "Le catalogue de voix est vide."}
          </p>
        </div>
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
