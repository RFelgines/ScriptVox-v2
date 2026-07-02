"use client";

import { useEffect, useRef, useState } from "react";
import {
  Gender,
  VoiceKind,
  VoiceSummary,
  createVoice,
  deleteVoice,
  listVoices,
  patchVoiceFavorite,
  requestVoiceSample,
  voiceSampleUrl,
} from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";
import Button from "@/components/ui/Button";
import VoiceOrb from "@/components/VoiceOrb";
import { buildHueMap } from "@/lib/voiceHues";

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

// Orbes agrandies (vs 96px avant) : moins par ligne, chacune mieux
// identifiable individuellement (demande explicite).
const ORB_SIZE = 160;

// POST /voices/{id}/sample répond 202 dès que la génération est dispatchée
// (audit 2026-07-02, Lot F1) — has_sample reste false dans cette réponse.
// On reinterroge la liste jusqu'à ce que la voix passe has_sample=true, plafonné
// pour ne pas poller indéfiniment si la génération échoue côté worker.
const SAMPLE_POLL_INTERVAL_MS = 3000;
const SAMPLE_POLL_MAX_ATTEMPTS = 20; // ~1 min

export default function VoixPage() {
  const { play, track, isPlaying } = usePlayer();
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [genderFilter, setGenderFilter] = useState<Gender | "ALL">("ALL");
  const [kindFilter, setKindFilter] = useState<VoiceKind | "ALL">("ALL");
  const [localeFilter, setLocaleFilter] = useState<string>("ALL");
  const [sampleFilter, setSampleFilter] = useState<"ALL" | "WITH" | "WITHOUT">("ALL");
  const [search, setSearch] = useState("");

  // ── Formulaire de clonage ──────────────────────────────────────────────────
  const [requestingId, setRequestingId] = useState<string | null>(null);

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
    const msg =
      voice.kind === "CLONED"
        ? `Supprimer la voix « ${voice.name} » ? Cette action est irréversible.`
        : `Retirer « ${voice.name} » du catalogue ? Elle sera restaurée au prochain redémarrage du serveur.`;
    if (!window.confirm(msg)) return;
    setDeletingId(voice.id);
    deleteVoice(voice.id)
      .then(() => setVoices((prev) => prev.filter((v) => v.id !== voice.id)))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setDeletingId(null));
  }

  // La génération de sample est dispatchée en tâche de fond côté serveur
  // (POST /voices/{id}/sample répond 202 immédiatement, has_sample reste false
  // dans la réponse) — on reinterroge la liste jusqu'à ce qu'elle passe à true.
  function pollForSample(voiceId: string, attempt = 0) {
    if (attempt >= SAMPLE_POLL_MAX_ATTEMPTS) {
      setRequestingId((cur) => (cur === voiceId ? null : cur));
      return;
    }
    setTimeout(() => {
      listVoices()
        .then((data) => {
          setVoices(data);
          const updated = data.find((v) => v.id === voiceId);
          if (updated?.has_sample) {
            setRequestingId((cur) => (cur === voiceId ? null : cur));
          } else {
            pollForSample(voiceId, attempt + 1);
          }
        })
        .catch(() => setRequestingId((cur) => (cur === voiceId ? null : cur)));
    }, SAMPLE_POLL_INTERVAL_MS);
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
      // Auto-génère le sample si pas encore disponible (TTS_PROVIDER=qwen)
      if (!created.has_sample && created.kind === "CLONED") {
        setRequestingId(created.id);
        requestVoiceSample(created.id)
          .then(() => pollForSample(created.id))
          .catch(() => setRequestingId(null));
      }
    } catch (err) {
      setCloneError(err instanceof Error ? err.message : String(err));
    } finally {
      setCloning(false);
    }
  }

  const localeOptions = Array.from(
    new Set(voices.map((v) => v.locale).filter((l): l is string => !!l)),
  ).sort();

  const searchQuery = search.trim().toLowerCase();

  const visible = voices
    .filter((v) => !favoritesOnly || v.is_favorite)
    .filter((v) => genderFilter === "ALL" || v.gender === genderFilter)
    .filter((v) => kindFilter === "ALL" || v.kind === kindFilter)
    .filter((v) => localeFilter === "ALL" || v.locale === localeFilter)
    .filter((v) => sampleFilter === "ALL" || (sampleFilter === "WITH" ? v.has_sample : !v.has_sample))
    .filter((v) => !searchQuery || v.name.toLowerCase().includes(searchQuery));

  const filtersActive =
    favoritesOnly ||
    genderFilter !== "ALL" ||
    kindFilter !== "ALL" ||
    localeFilter !== "ALL" ||
    sampleFilter !== "ALL" ||
    searchQuery !== "";
  // Calculé sur le catalogue complet (pas `visible`) : la couleur d'une voix
  // ne doit pas changer selon que le filtre "Favoris" est actif ou non.
  const orbHues = buildHueMap(voices);

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold">Voix</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher par nom…"
            aria-label="Rechercher une voix"
            className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm placeholder:text-muted"
          />
          <select
            value={genderFilter}
            onChange={(e) => setGenderFilter(e.target.value as Gender | "ALL")}
            aria-label="Filtrer par genre"
            className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
          >
            <option value="ALL">Tous genres</option>
            <option value="MALE">Masculin</option>
            <option value="FEMALE">Féminin</option>
            <option value="NEUTRAL">Neutre</option>
          </select>
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value as VoiceKind | "ALL")}
            aria-label="Filtrer par type"
            className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
          >
            <option value="ALL">Tous types</option>
            <option value="CATALOGUE">Catalogue</option>
            <option value="CLONED">Clonées</option>
          </select>
          {localeOptions.length > 0 && (
            <select
              value={localeFilter}
              onChange={(e) => setLocaleFilter(e.target.value)}
              aria-label="Filtrer par langue"
              className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
            >
              <option value="ALL">Toutes langues</option>
              {localeOptions.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          )}
          <select
            value={sampleFilter}
            onChange={(e) => setSampleFilter(e.target.value as "ALL" | "WITH" | "WITHOUT")}
            aria-label="Filtrer par aperçu"
            className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
          >
            <option value="ALL">Tous aperçus</option>
            <option value="WITH">Aperçu disponible</option>
            <option value="WITHOUT">Sans aperçu</option>
          </select>
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
          {filtersActive ? (
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
            {filtersActive ? "Aucune voix ne correspond" : "Aucune voix disponible"}
          </p>
          <p className="text-sm">
            {filtersActive
              ? "Essayez d'élargir les filtres ci-dessus."
              : "Le catalogue de voix est vide."}
          </p>
        </div>
      )}

      {visible.length > 0 && (
        <div className="mt-8 flex flex-wrap gap-x-8 gap-y-10">
          {visible.map((v) => (
            <div key={v.id} className="flex w-40 flex-col items-center gap-2">
              <div className="relative">
                {v.kind === "CLONED" && !v.has_sample ? (
                  <button
                    onClick={() => {
                      if (requestingId === v.id) return;
                      setRequestingId(v.id);
                      requestVoiceSample(v.id)
                        .then(() => pollForSample(v.id))
                        .catch((e) => {
                          setError(e instanceof Error ? e.message : String(e));
                          setRequestingId(null);
                        });
                    }}
                    aria-label={`Générer un aperçu pour ${v.name}`}
                    title="Sample non disponible — cliquer pour générer"
                    className="group grayscale opacity-50 transition-all hover:opacity-70"
                  >
                    <VoiceOrb hue={orbHues.get(v.id) ?? 0} size={ORB_SIZE}>
                      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/30 text-xl text-white opacity-0 transition-opacity group-hover:opacity-100">
                        {requestingId === v.id ? "…" : "↺"}
                      </span>
                    </VoiceOrb>
                  </button>
                ) : (
                  <button
                    onClick={() => play({ title: `Aperçu — ${v.name}`, src: voiceSampleUrl(v.id) })}
                    aria-label={`Écouter un aperçu de ${v.name}`}
                    className="group transition-transform hover:scale-105"
                  >
                    <VoiceOrb
                      hue={orbHues.get(v.id) ?? 0}
                      size={ORB_SIZE}
                      active={isPlaying && track?.src === voiceSampleUrl(v.id)}
                    >
                      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/30 text-white opacity-0 transition-opacity group-hover:opacity-100">
                        ▶
                      </span>
                    </VoiceOrb>
                  </button>
                )}
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
                <button
                  onClick={() => handleDeleteVoice(v)}
                  disabled={deletingId === v.id}
                  aria-label={`Supprimer la voix ${v.name}`}
                  title={v.kind === "CLONED" ? "Supprimer cette voix clonée" : "Retirer du catalogue"}
                  className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-surface text-xs text-muted shadow hover:bg-red-900/60 hover:text-red-300 disabled:opacity-50"
                >
                  {deletingId === v.id ? "…" : "×"}
                </button>
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
