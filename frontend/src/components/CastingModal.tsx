"use client";

import { useEffect, useState } from "react";
import {
  BookStatus,
  CharacterSummary,
  MergeSuggestion,
  VoiceSummary,
  acceptMergeSuggestion,
  listCharacters,
  listMergeSuggestions,
  listVoices,
  patchCharacterVoice,
  rejectMergeSuggestion,
  generateBook,
} from "@/lib/api";

export default function CastingModal({
  bookId,
  bookStatus,
  onClose,
  onGenerated,
}: {
  bookId: number;
  bookStatus: BookStatus;
  onClose: () => void;
  onGenerated: () => void;
}) {
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

  // Fetch initial (chaîne .then pour la règle react-hooks/set-state-in-effect).
  useEffect(() => {
    let active = true;
    Promise.all([listCharacters(bookId), listVoices(), listMergeSuggestions(bookId)])
      .then(([chars, vs, merges]) => {
        if (!active) return;
        setCharacters(chars);
        setVoices(vs);
        setMergeSuggestions(merges);
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

  // Fermeture au clavier (Esc).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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
      .then(() => {
        onGenerated();
        onClose();
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setGenerating(false);
      });
  }

  const assignable = voices.filter((v) => v.id !== "narrator");
  const canGenerate = bookStatus === "ANALYZED" && !generating;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Casting"
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-gray-800 bg-gray-900 text-gray-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-800 p-4">
          <h2 className="text-lg font-semibold">Casting des voix</h2>
          <button
            onClick={onClose}
            aria-label="Fermer"
            className="text-gray-400 hover:text-gray-200"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading && <p className="text-gray-500">Chargement…</p>}

          {error && (
            <div className="mb-4 rounded border border-red-700 bg-red-900/40 p-3">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          {mergeSuggestions.length > 0 && (
            <div className="mb-4 rounded border border-yellow-700 bg-yellow-900/20 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-semibold text-yellow-300">
                  Fusions de personnages suggérées
                </p>
                <button
                  onClick={handleAcceptAllMerges}
                  disabled={acceptingAll}
                  className="rounded bg-yellow-700 px-2 py-1 text-xs font-medium hover:bg-yellow-600 disabled:opacity-50"
                >
                  {acceptingAll ? "…" : "Tout accepter"}
                </button>
              </div>
              <ul className="space-y-2">
                {mergeSuggestions.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center gap-3 rounded bg-gray-950 p-2"
                  >
                    <div className="flex-1 text-sm">
                      <span className="font-medium">{characterName(s.survivor_character_id)}</span>
                      <span className="text-gray-500"> ← </span>
                      <span className="text-gray-400">{characterName(s.merged_character_id)}</span>
                      {s.reason && (
                        <p className="text-xs text-gray-500">{s.reason}</p>
                      )}
                    </div>
                    <button
                      onClick={() => handleResolveMerge(s.id, "accept")}
                      disabled={resolvingId === s.id || acceptingAll}
                      className="rounded bg-green-700 px-2 py-1 text-xs font-medium hover:bg-green-600 disabled:opacity-50"
                    >
                      Accepter
                    </button>
                    <button
                      onClick={() => handleResolveMerge(s.id, "reject")}
                      disabled={resolvingId === s.id || acceptingAll}
                      className="rounded bg-gray-700 px-2 py-1 text-xs font-medium hover:bg-gray-600 disabled:opacity-50"
                    >
                      Rejeter
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!loading && characters.length === 0 && !error && (
            <p className="text-gray-500">Aucun personnage détecté.</p>
          )}

          {characters.length > 0 && (
            <ul className="space-y-3">
              {characters.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center gap-3 rounded border border-gray-800 bg-gray-950 p-3"
                >
                  <div className="flex-1">
                    <p className="font-medium">{c.name}</p>
                    <p className="text-xs text-gray-500">
                      {c.gender}
                      {c.age_category && c.age_category !== "UNKNOWN"
                        ? ` · ${c.age_category}`
                        : ""}
                    </p>
                    {c.description && (
                      <p className="mt-1 line-clamp-2 text-xs text-gray-600">
                        {c.description}
                      </p>
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
                    {savingId === c.id && (
                      <span className="text-xs text-gray-500">…</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-gray-800 p-4">
          <p className="text-xs text-gray-500">
            {voices[0]?.locale
              ? `Langue : ${voices[0].locale}`
              : "Langue : selon le provider TTS"}
          </p>
          <button
            onClick={handleGenerate}
            disabled={!canGenerate}
            title={
              bookStatus === "ANALYZED"
                ? undefined
                : "Génération possible uniquement quand le livre est ANALYZED"
            }
            className="rounded bg-green-700 px-4 py-2 text-sm font-semibold hover:bg-green-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {generating ? "Lancement…" : "Générer l'audio"}
          </button>
        </div>
      </div>
    </div>
  );
}
