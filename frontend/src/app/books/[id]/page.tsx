"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  AppSettings,
  BookSummary,
  CharacterSummary,
  ChapterSummary,
  MergeSuggestion,
  VoiceSummary,
  acceptMergeSuggestion,
  analyzeBook,
  bookMp3Url,
  chapterAudioUrl,
  coverUrl,
  generateAllChapters,
  generateBook,
  generateChapter,
  getAppSettings,
  getBook,
  listCharacters,
  listChapters,
  listMergeSuggestions,
  listVoices,
  patchBookGenre,
  patchBookLanguage,
  patchBookProvider,
  patchBookPublishedAt,
  patchCharacterVoice,
  rejectMergeSuggestion,
  stopBook,
  voiceSampleUrl,
} from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import StatusBadge from "@/components/ui/StatusBadge";
import Button from "@/components/ui/Button";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";
import Select from "@/components/ui/Select";
import VoiceOrb from "@/components/VoiceOrb";
import { buildHueMap } from "@/lib/voiceHues";
import { useT } from "@/lib/i18n/LanguageContext";

const POLL_MS = 3000;

function bookActive(status: string): boolean {
  return status === "PENDING" || status === "PROCESSING" || status === "GENERATING";
}

function chapterActive(status: string): boolean {
  return status === "PENDING" || status === "GENERATING";
}

export default function BookDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bookId = Number(id);
  const { play } = usePlayer();
  const t = useT();

  const [book, setBook] = useState<BookSummary | null>(null);
  const [coverOk, setCoverOk] = useState(true);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingPos, setGeneratingPos] = useState<number | null>(null);
  const [generatingAll, setGeneratingAll] = useState(false);
  // Bumpé après une génération pour relancer le polling (l'effet s'arrête à
  // ANALYZED, qui n'est pas un état « actif »).
  const [reloadNonce, setReloadNonce] = useState(0);

  // ── Casting (fusionné dans la page livre — plus de page dédiée) ────────────
  const [castingExpanded, setCastingExpanded] = useState(false);
  const [castingLoaded, setCastingLoaded] = useState(false);
  const [castingLoading, setCastingLoading] = useState(false);
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [mergeSuggestions, setMergeSuggestions] = useState<MergeSuggestion[]>([]);
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [acceptingAll, setAcceptingAll] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [analyzingBook, setAnalyzingBook] = useState(false);
  const [stoppingBook, setStoppingBook] = useState(false);
  const [savingProvider, setSavingProvider] = useState(false);
  const [savingGenre, setSavingGenre] = useState(false);
  const [savingLanguage, setSavingLanguage] = useState(false);
  const [savingPublishedAt, setSavingPublishedAt] = useState(false);
  const [search, setSearch] = useState("");
  const [showSecondary, setShowSecondary] = useState(false);
  // Bumpé après une action de fusion pour relancer le fetch (personnages + suggestions).
  const [mergeReloadNonce, setMergeReloadNonce] = useState(0);
  // Voix sélectionnée dans le UI mais pas encore committée (pré-écoute).
  const [pendingVoices, setPendingVoices] = useState<Map<number, string>>(new Map());

  // ?casting=auto (posé par la bibliothèque après upload) : déplie la section
  // casting dès que l'analyse atteint ANALYZED, servant de confirmation
  // "tout valider ou ajuster" sans action de l'utilisateur. Lu manuellement via
  // window.location plutôt que useSearchParams pour éviter le besoin d'un
  // Suspense boundary (cf. doc Next : useSearchParams force le CSR jusqu'au
  // Suspense parent le plus proche pendant le prerendering).
  const [autoFlag] = useState(
    () =>
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("casting") === "auto",
  );

  useEffect(() => {
    if (!(autoFlag && book?.status === "ANALYZED" && !castingExpanded)) return;
    // setState différé en microtâche pour rester hors du corps synchrone de
    // l'effet (règle react-hooks/set-state-in-effect, même convention qu'ailleurs
    // dans ce projet).
    Promise.resolve().then(() => setCastingExpanded(true));
  }, [autoFlag, book?.status, castingExpanded]);

  useEffect(() => {
    if (!castingExpanded) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setCastingLoading(true);
    });
    Promise.all([
      listCharacters(bookId),
      listVoices(),
      listMergeSuggestions(bookId),
      getAppSettings(),
    ])
      .then(([chars, vs, merges, settings]) => {
        if (!active) return;
        setCharacters(chars);
        setVoices(vs);
        setMergeSuggestions(merges);
        setAppSettings(settings);
        setCastingLoaded(true);
        setError(null);
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setCastingLoading(false);
      });
    return () => {
      active = false;
    };
  }, [castingExpanded, bookId, mergeReloadNonce]);

  function handleProviderChange(value: string) {
    setSavingProvider(true);
    setError(null);
    patchBookProvider(bookId, value || null)
      .then((updated) => setBook(updated))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingProvider(false));
  }

  function handleGenreBlur(value: string) {
    if (!book) return;
    const next = value.trim() || null;
    if (next === (book.genre ?? null)) return;
    setSavingGenre(true);
    setError(null);
    patchBookGenre(bookId, next)
      .then((updated) => setBook(updated))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingGenre(false));
  }

  function handleLanguageBlur(value: string) {
    if (!book) return;
    const next = value.trim() || null;
    if (next === (book.language ?? null)) return;
    setSavingLanguage(true);
    setError(null);
    patchBookLanguage(bookId, next)
      .then((updated) => setBook(updated))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingLanguage(false));
  }

  function handlePublishedAtChange(value: string) {
    if (!book) return;
    const next = value || null;
    if (next === (book.published_at ?? null)) return;
    setSavingPublishedAt(true);
    setError(null);
    patchBookPublishedAt(bookId, next)
      .then((updated) => setBook(updated))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingPublishedAt(false));
  }

  function handleVoiceChange(characterId: number, voiceId: string) {
    setSavingId(characterId);
    setError(null);
    patchCharacterVoice(characterId, voiceId)
      .then((updated) => {
        // Fusionne uniquement voice_id : la réponse de PATCH ne recalcule pas
        // segment_count (calculé seulement par GET /characters), remplacer tout
        // l'objet écraserait ce champ à 0 et ferait basculer le personnage à
        // tort dans "personnages secondaires sans réplique".
        setCharacters((prev) =>
          prev.map((c) => (c.id === updated.id ? { ...c, voice_id: updated.voice_id } : c)),
        );
        setPendingVoices((prev) => { const m = new Map(prev); m.delete(characterId); return m; });
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingId(null));
  }

  function characterName(charId: number): string {
    return characters.find((c) => c.id === charId)?.name ?? `#${charId}`;
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

  function handleAnalyzeBook() {
    const destructive = book?.status === "ANALYZED" || book?.status === "DONE";
    if (destructive && !window.confirm(t.book.reanalyzeConfirm)) return;
    setAnalyzingBook(true);
    setError(null);
    analyzeBook(bookId)
      .then(() => setReloadNonce((n) => n + 1))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setAnalyzingBook(false));
  }

  function handleStopBook() {
    if (!window.confirm(t.book.stopConfirm)) return;
    setStoppingBook(true);
    setError(null);
    stopBook(bookId)
      .then((updated) => setBook(updated))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setStoppingBook(false));
  }

  function handleGenerateBook() {
    // force=true uniquement pour la régénération complète explicite depuis un
    // livre DONE (confirmation requise) -- sur ANALYZED, "Générer l'audio"
    // préserve désormais les chapitres déjà générés individuellement au lieu
    // de tout re-synthétiser (audit 2026-07-11, T2.1).
    const force = book?.status === "DONE";
    if (force && !window.confirm(t.book.regenerateAudioConfirm)) return;
    setGenerating(true);
    setError(null);
    generateBook(bookId, force)
      .then(() => setReloadNonce((n) => n + 1))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setGenerating(false));
  }

  function handleGenerateChapter(position: number) {
    setGeneratingPos(position);
    generateChapter(bookId, position)
      .then(() => setReloadNonce((n) => n + 1))
      .catch((e) => setError(String(e)))
      .finally(() => setGeneratingPos(null));
  }

  function handleGenerateAllChapters() {
    setGeneratingAll(true);
    generateAllChapters(bookId)
      .then(() => setReloadNonce((n) => n + 1))
      .catch((e) => setError(String(e)))
      .finally(() => setGeneratingAll(false));
  }

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    // setTimeout récursif (pas setInterval) : la prochaine requête n'est
    // planifiée qu'une fois la précédente résolue → aucun chevauchement.
    function tick() {
      Promise.all([getBook(bookId), listChapters(bookId)])
        .then(([b, ch]) => {
          if (!active) return;
          setBook(b);
          setChapters(ch);
          setError(null);
          const keep = bookActive(b.status) || ch.some((c) => chapterActive(c.status));
          if (keep) timer = setTimeout(tick, POLL_MS);
        })
        .catch((e) => {
          if (active) setError(String(e));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }

    tick();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [bookId, reloadNonce]);

  const effectiveProvider = book?.tts_provider ?? appSettings?.default_tts_provider ?? "edgetts";
  const voiceMap = new Map(voices.map((v) => [v.id, v]));
  // Même teinte que /voix et le player (angle d'or sur le catalogue complet) --
  // l'orbe du casting doit être reconnaissable comme "la même voix" ailleurs.
  const voiceHues = buildHueMap(voices);
  function isProviderCompatible(voiceId: string): boolean {
    const v = voiceMap.get(voiceId);
    if (!v) return true;
    return v.kind === "CATALOGUE" || effectiveProvider === "qwen";
  }
  const assignable = voices.filter(
    (v) => v.id !== "narrator" && (v.kind === "CATALOGUE" || effectiveProvider === "qwen"),
  );
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
        className="flex items-center gap-3 rounded-2xl bg-surface-2/60 p-3.5 transition-colors hover:bg-surface-2"
      >
        <div className="flex-1">
          <p className="font-medium">{c.name}</p>
          <p className="text-xs text-muted">
            {c.gender}
            {c.age_category && c.age_category !== "UNKNOWN" ? ` · ${c.age_category}` : ""}
            {c.segment_count > 0 ? ` · ${t.book.segmentCount(c.segment_count)}` : ""}
          </p>
          {c.description && (
            <p className="mt-1 line-clamp-2 text-xs text-muted">{c.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {c.voice_id && !isProviderCompatible(c.voice_id) && (
            <span
              title={t.book.clonedVoiceIncompatible(effectiveProvider)}
              className="text-amber-600"
            >
              <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4" aria-hidden="true">
                <path d="M8 1.5L1 14h14L8 1.5zM8 6v4M8 11.5v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
              </svg>
            </span>
          )}
          {c.voice_id && voiceMap.get(c.voice_id)?.kind === "CLONED" && (
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted whitespace-nowrap">
              {t.book.clonedBadge}
            </span>
          )}
          {(() => {
            const selectedVoiceId = pendingVoices.get(c.id) ?? c.voice_id;
            return selectedVoiceId ? (
              <VoiceOrb hue={voiceHues.get(selectedVoiceId) ?? 0} size={22} />
            ) : (
              <span className="h-[22px] w-[22px] shrink-0 rounded-full bg-surface-2" aria-hidden="true" />
            );
          })()}
          <Select
            value={pendingVoices.get(c.id) ?? c.voice_id ?? ""}
            disabled={savingId === c.id}
            placeholder={t.book.chooseVoice}
            onChange={(v) => setPendingVoices((prev) => new Map(prev).set(c.id, v))}
            options={[
              ...assignable
                .filter((v) => v.kind === "CATALOGUE")
                .map((v) => ({ value: v.id, label: `${v.name}${v.gender ? ` — ${v.gender}` : ""}` })),
              ...assignable
                .filter((v) => v.kind === "CLONED")
                .map((v) => ({
                  value: v.id,
                  label: `${v.name}${v.gender ? ` — ${v.gender}` : ""}`,
                  group: t.book.clonedVoicesGroup,
                })),
            ]}
          />
          {(pendingVoices.get(c.id) ?? c.voice_id) && (
            <button
              onClick={() => {
                const id = pendingVoices.get(c.id) ?? c.voice_id!;
                play({ title: t.book.previewTitle(id), src: voiceSampleUrl(id) });
              }}
              title={t.book.previewVoice}
              aria-label={t.book.previewVoice}
              className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-foreground"
            >
              <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5 ml-0.5">
                <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
              </svg>
            </button>
          )}
          {pendingVoices.has(c.id) && pendingVoices.get(c.id) !== c.voice_id && (
            <button
              onClick={() => handleVoiceChange(c.id, pendingVoices.get(c.id)!)}
              disabled={savingId === c.id}
              title={t.book.confirmVoice}
              aria-label={t.book.confirmVoice}
              className="rounded-full p-1.5 text-amber-600 hover:bg-amber-500/10 disabled:opacity-50"
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                <path d="M2.5 8.5l4 4 7-8" />
              </svg>
            </button>
          )}
          {savingId === c.id && <span className="text-xs text-muted">…</span>}
        </div>
      </li>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Link href="/" className="text-sm text-muted hover:text-foreground">
        {t.book.backToLibrary}
      </Link>

      {loading && !book && (
        <div className="mt-6 flex gap-6">
          <Skeleton className="aspect-[2/3] w-40 shrink-0 rounded-2xl sm:w-44" />
          <div className="flex flex-1 flex-col gap-3 pt-1">
            <Skeleton className="h-7 w-3/4 rounded" />
            <Skeleton className="h-4 w-1/3 rounded" />
            <Skeleton className="mt-1 h-6 w-20 rounded-full" />
          </div>
        </div>
      )}

      {error && (
        <Alert title={t.book.errorTitle} className="mt-6">
          <p className="mt-1 text-sm text-danger">{error}</p>
        </Alert>
      )}

      {book && (
        <>
          <header className="mt-6 flex flex-col items-center gap-4 text-center sm:flex-row sm:items-start sm:gap-8 sm:text-left">
            <div className="aspect-[2/3] w-40 shrink-0 overflow-hidden rounded-2xl bg-surface-2 shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)] sm:w-44">
              {book.cover_path && coverOk ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={coverUrl(book.id)}
                  alt={t.book.coverAlt(book.title)}
                  className="h-full w-full object-cover"
                  onError={() => setCoverOk(false)}
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center p-2 text-center text-xs text-muted">
                  {book.title}
                </div>
              )}
            </div>

            <div className="min-w-0 flex-1">
              <h1 className="font-display text-3xl font-medium tracking-tight sm:text-4xl">{book.title}</h1>
              {book.author && <p className="mt-1 text-muted">{book.author}</p>}
              <div className="mt-3 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                <StatusBadge status={book.status} />
                <input
                  key={`genre-${book.genre ?? ""}`}
                  type="text"
                  defaultValue={book.genre ?? ""}
                  onBlur={(e) => handleGenreBlur(e.target.value)}
                  disabled={savingGenre}
                  placeholder={t.book.genrePlaceholder}
                  aria-label={t.book.genreAriaLabel}
                  className="rounded-full border-none bg-surface-2 px-3 py-1 text-xs text-muted placeholder:text-muted/60 disabled:opacity-50"
                />
                <input
                  key={`language-${book.language ?? ""}`}
                  type="text"
                  defaultValue={book.language ?? ""}
                  onBlur={(e) => handleLanguageBlur(e.target.value)}
                  disabled={savingLanguage}
                  placeholder={t.book.languagePlaceholder}
                  aria-label={t.book.languageAriaLabel}
                  className="w-28 rounded-full border-none bg-surface-2 px-3 py-1 text-xs text-muted placeholder:text-muted/60 disabled:opacity-50"
                />
                <input
                  key={`published-${book.published_at ?? ""}`}
                  type="date"
                  defaultValue={book.published_at ?? ""}
                  onChange={(e) => handlePublishedAtChange(e.target.value)}
                  disabled={savingPublishedAt}
                  aria-label={t.book.publishedAtLabel}
                  title={t.book.publishedAtLabel}
                  className="rounded-full border-none bg-surface-2 px-3 py-1 text-xs text-muted disabled:opacity-50"
                />
              </div>
              {book.progress > 0 && book.progress < 100 && (
                <div className="mt-2 h-2 w-full max-w-md overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full bg-primary"
                    style={{ width: `${book.progress}%` }}
                  />
                </div>
              )}
              {book.status === "FAILED" && book.error_message && (
                <p className="mt-2 text-sm text-danger">{book.error_message}</p>
              )}
              {autoFlag && (book.status === "PENDING" || book.status === "PROCESSING") && (
                <p className="mt-2 text-sm text-muted">
                  {t.book.analysisInProgressHint}
                </p>
              )}

              {/* ── Barre d'actions ──────────────────────────────────────────── */}
              <div className="mt-3 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                {/* Analyser / Reprendre l'analyse */}
                {book.status === "PENDING" && (
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={analyzingBook}
                    onClick={handleAnalyzeBook}
                  >
                    {analyzingBook ? t.book.launching : t.book.analyze}
                  </Button>
                )}
                {book.status === "FAILED" && (
                  <div className="flex items-center gap-1.5">
                    {/* Le bouton PRIMAIRE suit book.failed_stage (audit 2026-07-11,
                        T2.3) : avant, "Reprendre l'analyse" était toujours mis en
                        avant même quand seule la GÉNÉRATION avait échoué -- un clic
                        dessus repassait le livre en ANALYZED, cassant la reprise de
                        génération en cours. Les deux boutons restent visibles
                        (chapters.length > 0 = les deux étapes sont possibles) --
                        seul le style change, pas de comportement caché. */}
                    <Button
                      variant={book.failed_stage === "generation" ? "secondary" : "primary"}
                      size="sm"
                      disabled={analyzingBook}
                      onClick={handleAnalyzeBook}
                    >
                      {analyzingBook ? t.book.launching : t.book.resumeAnalysis}
                    </Button>
                    {chapters.length > 0 && (
                      <Button
                        variant={book.failed_stage === "generation" ? "primary" : "secondary"}
                        size="sm"
                        disabled={generating}
                        onClick={handleGenerateBook}
                      >
                        {generating ? t.book.launching : t.book.resumeGeneration}
                      </Button>
                    )}
                    {book.error_message !== "Arrêté par l'utilisateur." && (
                      <span
                        title={t.book.analysisFailedTitle(book.error_message ?? "erreur inconnue")}
                        aria-label={t.book.analysisFailedAriaLabel}
                        className="text-warning"
                      >
                        ⚠️
                      </span>
                    )}
                  </div>
                )}
                {(book.status === "ANALYZED" || book.status === "DONE") && (
                  <Button
                    size="sm"
                    disabled={analyzingBook}
                    onClick={handleAnalyzeBook}
                  >
                    {analyzingBook ? t.book.launching : t.book.reanalyze}
                  </Button>
                )}

                {/* Générer / Regénérer l'audio */}
                {(book.status === "ANALYZED" || book.status === "DONE") && (
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={generating}
                    onClick={handleGenerateBook}
                  >
                    {generating
                      ? t.book.launching
                      : book.status === "DONE"
                      ? t.book.regenerateAudio
                      : t.book.generateAudio}
                  </Button>
                )}

                {/* Arrêter */}
                {(book.status === "PROCESSING" || book.status === "GENERATING") && (
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={stoppingBook}
                    onClick={handleStopBook}
                  >
                    {stoppingBook ? t.book.stopping : t.book.stop}
                  </Button>
                )}

                {/* Casting */}
                {(book.status === "ANALYZED" || book.status === "GENERATING" || book.status === "DONE") && (
                  <Button size="sm" onClick={() => setCastingExpanded((v) => !v)} className="inline-flex items-center gap-1.5">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                      className={`h-3.5 w-3.5 shrink-0 transition-transform duration-150 ${castingExpanded ? "rotate-90" : ""}`}>
                      <path d="M6 4l4 4-4 4" />
                    </svg>
                    {t.book.casting}
                  </Button>
                )}

                {/* Écouter */}
                {book.status === "DONE" && book.mp3_path && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() =>
                      play({
                        title: book.title,
                        src: bookMp3Url(book.id),
                        bookId: book.id,
                        bookTitle: book.title,
                        coverUrl: book.cover_path ? coverUrl(book.id) : undefined,
                      })
                    }
                    className="inline-flex items-center gap-1.5"
                  >
                    <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 ml-0.5 shrink-0">
                      <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
                    </svg>
                    {t.book.listen}
                  </Button>
                )}
              </div>
            </div>
          </header>

          {castingExpanded && (
            // Transition d'entrée seule (starting:, Tailwind v4) : la section
            // apparaissait sans aucun mouvement (audit UI/UX 2026-07-03).
            // Pas de transition de sortie -- démontage React instantané au clic,
            // cohérent avec le reste de l'app (pas de dépendance d'animation
            // ajoutée pour gérer un état "en cours de fermeture").
            <section className="mt-6 rounded-2xl bg-surface p-5 shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)] transition-all duration-200 ease-out starting:translate-y-1 starting:opacity-0">
              {castingLoading && !castingLoaded && (
                <p className="text-muted">{t.book.loadingCasting}</p>
              )}

              {castingLoaded && book.status !== "ANALYZED" && book.status !== "GENERATING" && book.status !== "DONE" && (
                <Alert title={t.book.castingUnavailableTitle}>
                  <p className="text-sm text-muted">
                    {t.book.castingUnavailableBody(book.status)}
                  </p>
                </Alert>
              )}

              {mergeSuggestions.length > 0 && (
                <div className="mb-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-sm font-semibold text-amber-600">
                      {t.book.mergeSuggestionsTitle}
                    </p>
                    <Button
                      variant="warning"
                      size="sm"
                      onClick={handleAcceptAllMerges}
                      disabled={acceptingAll}
                    >
                      {acceptingAll ? "…" : t.book.acceptAll}
                    </Button>
                  </div>
                  <ul className="space-y-2">
                    {mergeSuggestions.map((s) => (
                      <li key={s.id} className="flex items-center gap-3 rounded-xl bg-surface-2 p-2.5">
                        <div className="flex-1 text-sm">
                          <span className="font-medium">
                            {characterName(s.survivor_character_id)}
                          </span>
                          <span className="text-muted"> ← </span>
                          <span className="text-muted">
                            {characterName(s.merged_character_id)}
                          </span>
                          {s.reason && <p className="text-xs text-muted">{s.reason}</p>}
                        </div>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => handleResolveMerge(s.id, "accept")}
                          disabled={resolvingId === s.id || acceptingAll}
                        >
                          {t.book.accept}
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => handleResolveMerge(s.id, "reject")}
                          disabled={resolvingId === s.id || acceptingAll}
                        >
                          {t.book.reject}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {castingLoaded && characters.length === 0 && (
                <p className="text-muted">{t.book.noCharactersDetected}</p>
              )}

              {characters.length > 0 && (
                <>
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t.book.searchCharacterPlaceholder}
                    className="w-full rounded-full border-none bg-surface-2 px-4 py-2 text-sm placeholder:text-muted"
                  />

                  {mainCharacters.length > 0 ? (
                    <ul className="mt-4 space-y-3">{mainCharacters.map(renderCharacterRow)}</ul>
                  ) : (
                    <p className="mt-4 text-sm text-muted">{t.book.noCharacterMatches}</p>
                  )}

                  {secondaryCharacters.length > 0 && (
                    <div className="mt-6">
                      <button
                        onClick={() => setShowSecondary((v) => !v)}
                        className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground"
                      >
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                          className={`h-3.5 w-3.5 shrink-0 transition-transform duration-150 ${showSecondary ? "rotate-90" : ""}`}>
                          <path d="M6 4l4 4-4 4" />
                        </svg>
                        {t.book.secondaryCharacters(secondaryCharacters.length)}
                      </button>
                      {showSecondary && (
                        <ul className="mt-3 space-y-3">
                          {secondaryCharacters.map(renderCharacterRow)}
                        </ul>
                      )}
                    </div>
                  )}
                </>
              )}

              {castingLoaded && (
                <div className="mt-6 flex items-center justify-between gap-3 border-t border-border pt-4">
                  <div className="flex items-center gap-3">
                    <p className="text-xs text-muted">
                      {voices[0]?.locale
                        ? t.book.localeKnown(voices[0].locale)
                        : t.book.localeUnknown}
                    </p>
                    {appSettings && (
                      <label className="flex items-center gap-1.5 text-xs text-muted">
                        {t.book.engineLabel}
                        <Select
                          value={book.tts_provider ?? ""}
                          disabled={savingProvider}
                          onChange={handleProviderChange}
                          options={[
                            { value: "", label: t.book.defaultProvider(appSettings.default_tts_provider) },
                            ...appSettings.available_tts_providers.map((p) => ({ value: p, label: p })),
                          ]}
                        />
                      </label>
                    )}
                  </div>
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={handleGenerateBook}
                    disabled={!canGenerate}
                    title={
                      book.status === "ANALYZED"
                        ? undefined
                        : t.book.generateOnlyWhenAnalyzed
                    }
                  >
                    {generating ? t.book.launching : t.book.generateAudio}
                  </Button>
                </div>
              )}
            </section>
          )}

          <section className="mt-10">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-display text-2xl font-medium tracking-tight">
                {t.book.chaptersTitle(chapters.length)}
              </h2>
              {book.status === "ANALYZED" &&
                chapters.some((c) => c.status !== "DONE") && (
                  <Button
                    variant="warning"
                    onClick={handleGenerateAllChapters}
                    disabled={generatingAll}
                  >
                    {generatingAll ? "…" : t.book.generateAllAudio}
                  </Button>
                )}
            </div>
            {chapters.length === 0 ? (
              <p className="text-muted">{t.book.noChaptersYet}</p>
            ) : (
              <ul className="space-y-2.5">
                {chapters.map((ch) => (
                  <li
                    key={ch.id}
                    className="flex items-center gap-3 rounded-2xl bg-surface-2/60 p-3.5 transition-colors hover:bg-surface-2"
                  >
                    <span className="w-8 text-right text-xs text-muted">
                      {ch.position}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm">{ch.title ?? t.book.chapterFallback(ch.position)}</p>
                      {ch.status === "FAILED" && ch.error_message && (
                        <p className="text-xs text-danger">{ch.error_message}</p>
                      )}
                    </div>
                    <StatusBadge status={ch.status} className="text-xs" />
                    {book.status === "ANALYZED" && ch.status !== "DONE" && (
                      <Button
                        size="sm"
                        onClick={() => handleGenerateChapter(ch.position)}
                        disabled={generatingPos === ch.position || ch.status === "GENERATING"}
                      >
                        {generatingPos === ch.position ? "…" : t.book.generateChapter}
                      </Button>
                    )}
                    {ch.status === "DONE" && (
                      <>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() =>
                            play({
                              title: `${book.title} — ${ch.title ?? t.book.chapterFallback(ch.position)}`,
                              src: chapterAudioUrl(book.id, ch.position),
                              bookId: book.id,
                              bookTitle: book.title,
                              coverUrl: book.cover_path ? coverUrl(book.id) : undefined,
                              chapterPosition: ch.position,
                            })
                          }
                          className="inline-flex items-center gap-1"
                        >
                          <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 ml-0.5 shrink-0">
                            <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
                          </svg>
                          {t.book.listen}
                        </Button>
                        {book.status === "ANALYZED" && (
                          <Button
                            size="sm"
                            onClick={() => handleGenerateChapter(ch.position)}
                            disabled={generatingPos === ch.position}
                            title={t.book.regenerateChapter}
                          >
                            {generatingPos === ch.position ? "…" : "↺"}
                          </Button>
                        )}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
