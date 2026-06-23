"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AppSettings,
  BookSummary,
  CharacterSummary,
  MergeSuggestion,
  VoiceSummary,
  acceptMergeSuggestion,
  generateBook,
  getAppSettings,
  getBook,
  listCharacters,
  listMergeSuggestions,
  listVoices,
  patchBookProvider,
  patchCharacterVoice,
  rejectMergeSuggestion,
  voiceSampleUrl,
} from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import Button from "@/components/ui/Button";
import Alert from "@/components/ui/Alert";

export default function CastingPage({
  params,
}: {
  params: Promise<{ bookId: string }>;
}) {
  const { bookId: bookIdParam } = use(params);
  const bookId = Number(bookIdParam);
  const router = useRouter();
  const { play } = usePlayer();

  const [book, setBook] = useState<BookSummary | null>(null);
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [mergeSuggestions, setMergeSuggestions] = useState<MergeSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [acceptingAll, setAcceptingAll] = useState(false);
  const [generating, setGenerating] = useState(false);
  // Bumpé après une action de fusion pour relancer le fetch (personnages + suggestions).
  const [mergeReloadNonce, setMergeReloadNonce] = useState(0);
  const [search, setSearch] = useState("");
  const [showSecondary, setShowSecondary] = useState(false);
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null);
  const [savingProvider, setSavingProvider] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      getBook(bookId),
      listCharacters(bookId),
      listVoices(),
      listMergeSuggestions(bookId),
      getAppSettings(),
    ])
      .then(([b, chars, vs, merges, settings]) => {
        if (!active) return;
        setBook(b);
        setCharacters(chars);
        setVoices(vs);
        setMergeSuggestions(merges);
        setAppSettings(settings);
        setError(null);
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [bookId, mergeReloadNonce]);

  function handleProviderChange(value: string) {
    setSavingProvider(true);
    setError(null);
    patchBookProvider(bookId, value || null)
      .then((updated) => setBook(updated))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingProvider(false));
  }

  function handleVoiceChange(characterId: number, voiceId: string) {
    setSavingId(characterId);
    setError(null);
    patchCharacterVoice(characterId, voiceId)
      .then((updated) => {
        setCharacters((prev) =>
          prev.map((c) => (c.id === updated.id ? updated : c)),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingId(null));
  }

  function characterName(id: number): string {
    return characters.find((c) => c.id === id)?.name ?? `#${id}`;
  }

  function handleResolveMerge(suggestionId: number, action: "accept" | "reject") {
    setResolvingId(suggestionId);
    setError(null);
    const resolve = action === "accept" ? acceptMergeSuggestion : rejectMergeSuggestion;
    resolve(suggestionId)
      .then(() => setMergeReloadNonce((n) => n + 1))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setResolvingId(null));
  }

  function handleAcceptAllMerges() {
    setAcceptingAll(true);
    setError(null);
    // Séquentiel : accepter une suggestion peut en rejeter automatiquement une autre du
    // même groupe côté backend (doublon 3+) — un 409 sur une suggestion déjà résolue par
    // ce mécanisme est attendu, pas une vraie erreur, donc ignoré silencieusement ici.
    mergeSuggestions
      .reduce<Promise<void>>(
        (chain, s) =>
          chain.then(() => acceptMergeSuggestion(s.id).then(
            () => undefined,
            () => undefined,
          )),
        Promise.resolve(),
      )
      .then(() => setMergeReloadNonce((n) => n + 1))
      .finally(() => setAcceptingAll(false));
  }

  function handleGenerate() {
    setGenerating(true);
    setError(null);
    generateBook(bookId)
      .then(() => router.push(`/books/${bookId}`))
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setGenerating(false);
      });
  }

  const assignable = voices.filter((v) => v.id !== "narrator");
  const canGenerate = book?.status === "ANALYZED" && !generating;

  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? characters.filter((c) => c.name.toLowerCase().includes(needle))
    : characters;
  // Tri par importance narrative (nb de répliques) plutôt que l'ordre DB arbitraire.
  const mainCharacters = filtered
    .filter((c) => c.segment_count > 0)
    .sort((a, b) => b.segment_count - a.segment_count);
  // "Bruit" : personnages détectés sans aucune réplique (ex. dédicace) — repliés par
  // défaut plutôt que masqués, l'utilisateur peut vouloir leur assigner une voix.
  const secondaryCharacters = filtered.filter((c) => c.segment_count === 0);

  function renderCharacterRow(c: CharacterSummary) {
    return (
      <li
        key={c.id}
        className="flex items-center gap-3 rounded border border-gray-800 bg-gray-900 p-3"
      >
        <div className="flex-1">
          <p className="font-medium">{c.name}</p>
          <p className="text-xs text-gray-500">
            {c.gender}
            {c.age_category && c.age_category !== "UNKNOWN" ? ` · ${c.age_category}` : ""}
            {c.segment_count > 0
              ? ` · ${c.segment_count} réplique${c.segment_count > 1 ? "s" : ""}`
              : ""}
          </p>
          {c.description && (
            <p className="mt-1 line-clamp-2 text-xs text-gray-600">{c.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={c.voice_id ?? ""}
            disabled={savingId === c.id}
            onChange={(e) => handleVoiceChange(c.id, e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm disabled:opacity-50"
          >
            <option value="" disabled>
              Choisir…
            </option>
            {assignable.map((v) => (
              <option key={v.id} value={v.id}>
                {v.id}
                {v.gender ? ` — ${v.gender}` : ""}
              </option>
            ))}
          </select>
          {c.voice_id && (
            <button
              onClick={() =>
                play({ title: `Aperçu — ${c.voice_id}`, src: voiceSampleUrl(c.voice_id!) })
              }
              title="Écouter un aperçu de cette voix"
              aria-label="Écouter un aperçu de cette voix"
              className="rounded p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-100"
            >
              ▶
            </button>
          )}
          {savingId === c.id && <span className="text-xs text-gray-500">…</span>}
        </div>
      </li>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Link href={`/books/${bookId}`} className="text-sm text-gray-400 hover:text-gray-200">
        ← {book ? book.title : "Retour"}
      </Link>

      <h1 className="mt-3 text-2xl font-bold">Casting des voix</h1>

      {loading && <p className="mt-6 text-gray-500">Chargement…</p>}

      {error && (
        <Alert className="mt-4 p-3!">
          <p className="text-sm text-red-400">{error}</p>
        </Alert>
      )}

      {!loading && book && book.status !== "ANALYZED" && book.status !== "GENERATING" && book.status !== "DONE" && (
        <Alert title="Casting indisponible" className="mt-4">
          <p className="text-sm text-gray-400">
            Le casting n&apos;est disponible qu&apos;une fois le livre analysé (statut actuel :{" "}
            {book.status}).
          </p>
        </Alert>
      )}

      {mergeSuggestions.length > 0 && (
        <div className="mt-6 rounded border border-yellow-700 bg-yellow-900/20 p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-semibold text-yellow-300">
              Fusions de personnages suggérées
            </p>
            <Button
              variant="warning"
              size="sm"
              onClick={handleAcceptAllMerges}
              disabled={acceptingAll}
              className="bg-yellow-700 hover:bg-yellow-600"
            >
              {acceptingAll ? "…" : "Tout accepter"}
            </Button>
          </div>
          <ul className="space-y-2">
            {mergeSuggestions.map((s) => (
              <li key={s.id} className="flex items-center gap-3 rounded bg-gray-950 p-2">
                <div className="flex-1 text-sm">
                  <span className="font-medium">{characterName(s.survivor_character_id)}</span>
                  <span className="text-gray-500"> ← </span>
                  <span className="text-gray-400">{characterName(s.merged_character_id)}</span>
                  {s.reason && <p className="text-xs text-gray-500">{s.reason}</p>}
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleResolveMerge(s.id, "accept")}
                  disabled={resolvingId === s.id || acceptingAll}
                >
                  Accepter
                </Button>
                <Button
                  size="sm"
                  onClick={() => handleResolveMerge(s.id, "reject")}
                  disabled={resolvingId === s.id || acceptingAll}
                  className="bg-gray-700 hover:bg-gray-600"
                >
                  Rejeter
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!loading && characters.length === 0 && !error && (
        <p className="mt-6 text-gray-500">Aucun personnage détecté.</p>
      )}

      {characters.length > 0 && (
        <>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un personnage…"
            className="mt-6 w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-sm placeholder:text-gray-500"
          />

          {mainCharacters.length > 0 ? (
            <ul className="mt-4 space-y-3">{mainCharacters.map(renderCharacterRow)}</ul>
          ) : (
            <p className="mt-4 text-sm text-gray-500">Aucun personnage ne correspond.</p>
          )}

          {secondaryCharacters.length > 0 && (
            <div className="mt-6">
              <button
                onClick={() => setShowSecondary((v) => !v)}
                className="text-sm text-gray-500 hover:text-gray-300"
              >
                {showSecondary ? "▾" : "▸"} Personnages secondaires sans réplique (
                {secondaryCharacters.length})
              </button>
              {showSecondary && (
                <ul className="mt-3 space-y-3">{secondaryCharacters.map(renderCharacterRow)}</ul>
              )}
            </div>
          )}
        </>
      )}

      <div className="mt-8 flex items-center justify-between gap-3 border-t border-gray-800 pt-4">
        <div className="flex items-center gap-3">
          <p className="text-xs text-gray-500">
            {voices[0]?.locale ? `Langue : ${voices[0].locale}` : "Langue : selon le provider TTS"}
          </p>
          {appSettings && (
            <label className="flex items-center gap-1.5 text-xs text-gray-500">
              Moteur :
              <select
                value={book?.tts_provider ?? ""}
                disabled={savingProvider}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="rounded border border-gray-700 bg-gray-800 px-1.5 py-1 text-xs text-gray-200 disabled:opacity-50"
              >
                <option value="">Par défaut ({appSettings.default_tts_provider})</option>
                {appSettings.available_tts_providers.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <Button
          variant="primary"
          size="lg"
          onClick={handleGenerate}
          disabled={!canGenerate}
          title={
            book?.status === "ANALYZED"
              ? undefined
              : "Génération possible uniquement quand le livre est ANALYZED"
          }
          className="disabled:opacity-40!"
        >
          {generating ? "Lancement…" : "Générer l'audio"}
        </Button>
      </div>
    </main>
  );
}
