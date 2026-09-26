"use client";

import { use, useEffect, useRef, useState } from "react";
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
  bookM4bUrl,
  bookMp3Url,
  chapterAudioUrl,
  characterPreviewReady,
  characterPreviewUrl,
  coverUrl,
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
  patchChapterIncluded,
  rejectMergeSuggestion,
  requestCharacterPreview,
  stopBook,
} from "@/lib/api";
import { usePlayer } from "@/components/player/PlayerProvider";
import StatusBadge from "@/components/ui/StatusBadge";
import Button from "@/components/ui/Button";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";
import Select from "@/components/ui/Select";
import { useFeedback } from "@/components/ui/Feedback";
import BookStepper from "@/components/book/BookStepper";
import BookProgress from "@/components/book/BookProgress";
import MoreMenu, { MenuItem } from "@/components/book/MoreMenu";
import ChapterList from "@/components/book/ChapterList";
import CharacterRow from "@/components/book/CharacterRow";
import { buildHueMap } from "@/lib/voiceHues";
import { formatClock, getResume, type ResumePoint } from "@/lib/resume";
import { useT } from "@/lib/i18n/LanguageContext";

const POLL_MS = 3000;

function bookActive(status: string): boolean {
  return status === "PENDING" || status === "PROCESSING" || status === "GENERATING";
}

function chapterActive(status: string): boolean {
  return status === "PENDING" || status === "GENERATING";
}

// Valeur du sélecteur de langue : « fr-FR » -> fr, « en-US » -> en, le reste -> Auto.
function languageChoice(language: string | null): string {
  const l = (language ?? "").toLowerCase();
  if (l.startsWith("fr")) return "fr";
  if (l.startsWith("en")) return "en";
  return "";
}

export default function BookDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bookId = Number(id);
  const { play } = usePlayer();
  const { toast, confirm } = useFeedback();
  const t = useT();

  const [book, setBook] = useState<BookSummary | null>(null);
  const [coverOk, setCoverOk] = useState(true);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingPos, setGeneratingPos] = useState<number | null>(null);
  // Bumpé après une action pour relancer le polling (l'effet s'arrête à ANALYZED / DONE,
  // qui ne sont pas des états « actifs »).
  const [reloadNonce, setReloadNonce] = useState(0);
  const prevBookStatusRef = useRef<string | null>(null);

  // ── Casting (affiché d'office dès que l'analyse est terminée) ───────────────
  const [castingExpanded, setCastingExpanded] = useState(false);
  const [castingUserClosed, setCastingUserClosed] = useState(false);
  const [castingLoaded, setCastingLoaded] = useState(false);
  const [castingLoading, setCastingLoading] = useState(false);
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [mergeSuggestions, setMergeSuggestions] = useState<MergeSuggestion[]>([]);
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [previewingId, setPreviewingId] = useState<number | null>(null);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [acceptingAll, setAcceptingAll] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [analyzingBook, setAnalyzingBook] = useState(false);
  const [stoppingBook, setStoppingBook] = useState(false);
  const [savingProvider, setSavingProvider] = useState(false);
  const [search, setSearch] = useState("");
  const [showSecondary, setShowSecondary] = useState(false);
  // Bumpé après une action de fusion pour relancer le fetch (personnages + suggestions).
  const [mergeReloadNonce, setMergeReloadNonce] = useState(0);
  const [resumePoint, setResumePoint] = useState<ResumePoint | null>(null);

  // Réglages globaux (moteur effectif, avertissements de confidentialité).
  useEffect(() => {
    getAppSettings()
      .then(setAppSettings)
      .catch(() => {});
  }, []);

  // Dernière position d'écoute de ce livre (localStorage, lu après l'hydratation).
  useEffect(() => {
    Promise.resolve().then(() => setResumePoint(getResume(bookId)));
  }, [bookId, book?.status]);

  // Casting ouvert d'office dès que le livre est ANALYZED, sauf si l'utilisateur l'a replié.
  useEffect(() => {
    if (!(book?.status === "ANALYZED" && !castingExpanded && !castingUserClosed)) return;
    // setState différé en microtâche pour rester hors du corps synchrone de l'effet.
    Promise.resolve().then(() => setCastingExpanded(true));
  }, [book?.status, castingExpanded, castingUserClosed]);

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

  const voiceMap = new Map(voices.map((v) => [v.id, v]));
  // Même teinte que /voix et le player (angle d'or sur le catalogue complet) --
  // l'orbe du casting doit être reconnaissable comme "la même voix" ailleurs.
  const voiceHues = buildHueMap(voices);
  const effectiveProvider =
    book?.tts_provider ??
    appSettings?.preferred_tts_provider ??
    appSettings?.default_tts_provider ??
    "edgetts";
  const effectiveLlm =
    appSettings?.preferred_llm_provider ?? appSettings?.default_llm_provider ?? "ollama";
  const assignable = voices.filter(
    (v) => v.id !== "narrator" && (v.kind === "CATALOGUE" || effectiveProvider === "qwen"),
  );

  function fail(e: unknown) {
    toast(e instanceof Error ? e.message : String(e), { tone: "error" });
  }

  function handleProviderChange(value: string) {
    setSavingProvider(true);
    patchBookProvider(bookId, value || null)
      .then((updated) => setBook(updated))
      .catch(fail)
      .finally(() => setSavingProvider(false));
  }

  function handleGenreBlur(value: string) {
    if (!book) return;
    const next = value.trim() || null;
    if (next === (book.genre ?? null)) return;
    patchBookGenre(bookId, next)
      .then((updated) => setBook(updated))
      .catch(fail);
  }

  function handleLanguageChange(value: string) {
    patchBookLanguage(bookId, value || null)
      .then((updated) => setBook(updated))
      .catch(fail);
  }

  function handlePublishedAtChange(value: string) {
    if (!book) return;
    const next = value || null;
    if (next === (book.published_at ?? null)) return;
    patchBookPublishedAt(bookId, next)
      .then((updated) => setBook(updated))
      .catch(fail);
  }

  // Voix enregistrée immédiatement ; « Annuler » du toast rétablit la précédente.
  function handleVoiceChange(characterId: number, voiceId: string) {
    const target = characters.find((c) => c.id === characterId);
    const previous = target?.voice_id ?? null;
    if (voiceId === previous) return;
    setSavingId(characterId);
    patchCharacterVoice(characterId, voiceId)
      .then((updated) => {
        // Fusionne uniquement voice_id : la réponse de PATCH ne recalcule pas
        // segment_count (calculé seulement par GET /characters), remplacer tout
        // l'objet écraserait ce champ à 0 et ferait basculer le personnage à
        // tort dans "personnages secondaires sans réplique".
        setCharacters((prev) =>
          prev.map((c) => (c.id === updated.id ? { ...c, voice_id: updated.voice_id } : c)),
        );
        const voiceName = voiceMap.get(voiceId)?.name ?? voiceId;
        toast(
          t.flow.voiceSaved(target?.name ?? `#${characterId}`, voiceName),
          previous
            ? { action: { label: t.feedback.undo, onClick: () => handleVoiceChange(characterId, previous) } }
            : undefined,
        );
      })
      .catch(fail)
      .finally(() => setSavingId(null));
  }

  // Aperçu de la voix choisie sur une réplique du personnage : tâche courte et prioritaire côté
  // worker, réinterrogée jusqu'à ce que le fichier existe (60 s max).
  async function handlePreview(c: CharacterSummary) {
    if (!c.voice_id) return;
    const voiceId = c.voice_id;
    setPreviewingId(c.id);
    try {
      const { ready } = await requestCharacterPreview(c.id, voiceId);
      let ok = ready;
      for (let i = 0; !ok && i < 40; i++) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        ok = await characterPreviewReady(c.id, voiceId);
      }
      if (!ok) throw new Error(t.flow.previewFailed);
      play({
        title: t.book.previewTitle(`${c.name} — ${voiceMap.get(voiceId)?.name ?? voiceId}`),
        src: characterPreviewUrl(c.id, voiceId),
      });
    } catch (e) {
      fail(e instanceof Error ? e : new Error(t.flow.previewFailed));
    } finally {
      setPreviewingId(null);
    }
  }

  function characterName(charId: number): string {
    return characters.find((c) => c.id === charId)?.name ?? `#${charId}`;
  }

  function handleResolveMerge(suggestionId: number, action: "accept" | "reject") {
    setResolvingId(suggestionId);
    const resolve = action === "accept" ? acceptMergeSuggestion : rejectMergeSuggestion;
    resolve(suggestionId)
      .then(() => setMergeReloadNonce((n) => n + 1))
      .catch(fail)
      .finally(() => setResolvingId(null));
  }

  function handleAcceptAllMerges() {
    setAcceptingAll(true);
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

  async function handleAnalyzeBook(opts: { destructive?: boolean; force?: boolean } = {}) {
    if (opts.destructive) {
      const ok = await confirm({ title: t.book.reanalyzeConfirm, danger: true });
      if (!ok) return;
    }
    setAnalyzingBook(true);
    analyzeBook(bookId, opts.force === true)
      .then(() => setReloadNonce((n) => n + 1))
      .catch(fail)
      .finally(() => setAnalyzingBook(false));
  }

  async function handleStopBook() {
    const ok = await confirm({ title: t.book.stopConfirm, danger: true });
    if (!ok) return;
    setStoppingBook(true);
    stopBook(bookId)
      .then((updated) => setBook(updated))
      .catch(fail)
      .finally(() => setStoppingBook(false));
  }

  // force=true : régénération complète explicite d'un livre terminé (confirmation requise).
  // Sans force, les chapitres déjà générés sont conservés et seul le manquant est produit.
  async function handleGenerateBook(force = false) {
    if (force) {
      const ok = await confirm({ title: t.book.regenerateAudioConfirm, danger: true });
      if (!ok) return;
    }
    setGenerating(true);
    generateBook(bookId, force)
      .then(() => setReloadNonce((n) => n + 1))
      .catch(fail)
      .finally(() => setGenerating(false));
  }

  function handleGenerateChapter(position: number) {
    setGeneratingPos(position);
    generateChapter(bookId, position)
      .then(() => setReloadNonce((n) => n + 1))
      .catch(fail)
      .finally(() => setGeneratingPos(null));
  }

  function handleToggleIncluded(position: number, included: boolean) {
    patchChapterIncluded(bookId, position, included)
      .then((updated) =>
        setChapters((prev) => prev.map((c) => (c.position === updated.position ? updated : c))),
      )
      .catch(fail);
  }

  function playChapter(ch: ChapterSummary, startAt?: number) {
    if (!book) return;
    play({
      title: `${book.title} — ${ch.title ?? t.book.chapterFallback(ch.position)}`,
      src: chapterAudioUrl(book.id, ch.position),
      bookId: book.id,
      bookTitle: book.title,
      coverUrl: book.cover_path ? coverUrl(book.id) : undefined,
      chapterPosition: ch.position,
      startAt,
    });
  }

  // « Écouter » : reprend là où l'écoute s'est arrêtée, sinon au premier chapitre terminé.
  // Les chapitres s'enchaînent ensuite tout seuls (voir PlayerProvider).
  function handleListenBook() {
    if (!book) return;
    const listenable = chapters.filter((c) => c.status === "DONE" && c.included);
    if (listenable.length === 0) {
      if (book.mp3_path) {
        play({
          title: book.title,
          src: bookMp3Url(book.id),
          bookId: book.id,
          bookTitle: book.title,
          coverUrl: book.cover_path ? coverUrl(book.id) : undefined,
        });
      }
      return;
    }
    const saved = resumePoint ? listenable.find((c) => c.position === resumePoint.chapterPosition) : undefined;
    if (saved && resumePoint) {
      playChapter(saved, resumePoint.time);
    } else {
      playChapter(listenable[0]);
    }
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
          if (prevBookStatusRef.current !== null && prevBookStatusRef.current !== "ANALYZED" && b.status === "ANALYZED") {
            setMergeReloadNonce((n) => n + 1);
          }
          prevBookStatusRef.current = b.status;
          setChapters(ch);
          setError(null);
          const keep = bookActive(b.status) || ch.some((c) => chapterActive(c.status));
          if (keep) timer = setTimeout(tick, POLL_MS);
        })
        .catch((e) => {
          if (!active) return;
          setError(String(e));
          timer = setTimeout(tick, POLL_MS * 2);
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
      <CharacterRow
        key={c.id}
        character={c}
        assignable={assignable}
        voiceMap={voiceMap}
        voiceHues={voiceHues}
        effectiveProvider={effectiveProvider}
        saving={savingId === c.id}
        previewing={previewingId === c.id}
        onVoiceChange={handleVoiceChange}
        onPreview={handlePreview}
      />
    );
  }

  const resumeChapter = resumePoint
    ? chapters.find((c) => c.position === resumePoint.chapterPosition && c.status === "DONE")
    : undefined;
  const listenLabel =
    resumePoint && resumeChapter
      ? t.flow.resumeListening(
          resumeChapter.title ?? t.book.chapterFallback(resumeChapter.position),
          formatClock(resumePoint.time),
        )
      : t.flow.listen;

  const showCastingSection =
    castingExpanded && book !== null &&
    (book.status === "ANALYZED" || book.status === "GENERATING" || book.status === "DONE");

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
              </div>

              <BookProgress book={book} chapters={chapters} />

              {book.status === "FAILED" && book.error_message && (
                <p className="mt-2 text-sm text-danger">{book.error_message}</p>
              )}
              {(book.status === "PENDING" || book.status === "PROCESSING") && (
                <p className="mt-2 text-sm text-muted">{t.book.analysisInProgressHint}</p>
              )}
              {appSettings &&
                (book.status === "PENDING" || book.status === "PROCESSING") &&
                effectiveLlm === "gemini" && (
                  <p className="mt-1 text-xs text-muted">{t.flow.privacyCloudLlm}</p>
                )}
              {appSettings && book.status === "ANALYZED" && effectiveProvider === "edgetts" && (
                <p className="mt-2 text-xs text-muted">{t.flow.privacyCloudTts}</p>
              )}

              {/* ── Actions : UNE action principale selon l'état, le reste dans des menus ── */}
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                {book.status === "PENDING" && (
                  <Button
                    variant="primary"
                    size="lg"
                    disabled={analyzingBook}
                    onClick={() => handleAnalyzeBook()}
                  >
                    {analyzingBook ? t.book.launching : t.book.analyze}
                  </Button>
                )}

                {book.status === "ANALYZED" && (
                  <Button
                    variant="primary"
                    size="lg"
                    disabled={generating}
                    onClick={() => handleGenerateBook(false)}
                  >
                    {generating ? t.book.launching : t.flow.generateBook}
                  </Button>
                )}

                {book.status === "DONE" && (
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={handleListenBook}
                    className="inline-flex items-center gap-2"
                  >
                    <svg viewBox="0 0 16 16" fill="currentColor" className="ml-0.5 h-3.5 w-3.5 shrink-0">
                      <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
                    </svg>
                    {listenLabel}
                  </Button>
                )}

                {book.status === "FAILED" && (
                  <Button
                    variant="primary"
                    size="lg"
                    disabled={analyzingBook || generating}
                    onClick={() =>
                      book.failed_stage === "generation" && chapters.length > 0
                        ? handleGenerateBook(false)
                        : handleAnalyzeBook()
                    }
                  >
                    {analyzingBook || generating ? t.book.launching : t.flow.resume}
                  </Button>
                )}

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

                {book.status === "DONE" && (
                  <MoreMenu label={`${t.flow.download} ▾`}>
                    {book.m4b_path ? (
                      <MenuItem href={bookM4bUrl(book.id)}>{t.flow.downloadM4b}</MenuItem>
                    ) : (
                      <MenuItem disabled title={t.flow.m4bMissing}>
                        {t.flow.downloadM4b}
                      </MenuItem>
                    )}
                    {book.mp3_path && (
                      <MenuItem href={bookMp3Url(book.id)}>{t.flow.downloadMp3}</MenuItem>
                    )}
                  </MoreMenu>
                )}

                {(book.status === "ANALYZED" || book.status === "DONE" || book.status === "FAILED") && (
                  <MoreMenu label={`${t.flow.more} ▾`}>
                    {book.status === "DONE" && (
                      <MenuItem onClick={() => handleGenerateBook(true)}>{t.flow.regenerate}</MenuItem>
                    )}
                    {book.status !== "FAILED" && (
                      <MenuItem onClick={() => handleAnalyzeBook({ destructive: true })}>
                        {t.book.reanalyze}
                      </MenuItem>
                    )}
                    {book.status === "FAILED" && chapters.length > 0 && (
                      <MenuItem onClick={() => handleAnalyzeBook()}>{t.book.resumeAnalysis}</MenuItem>
                    )}
                    {book.status === "FAILED" && (
                      <MenuItem onClick={() => handleAnalyzeBook({ force: true })} danger>
                        {t.flow.restart}
                      </MenuItem>
                    )}
                    {(book.status === "ANALYZED" || book.status === "DONE") && (
                      <MenuItem
                        onClick={() => {
                          setCastingUserClosed(castingExpanded);
                          setCastingExpanded((v) => !v);
                        }}
                      >
                        {t.book.casting}
                      </MenuItem>
                    )}
                  </MoreMenu>
                )}
              </div>

              {/* Métadonnées : repliées par défaut (rarement modifiées). */}
              <details className="mt-4 text-left">
                <summary className="cursor-pointer text-xs text-muted hover:text-foreground">
                  {t.flow.details}
                </summary>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input
                    key={`genre-${book.genre ?? ""}`}
                    type="text"
                    defaultValue={book.genre ?? ""}
                    onBlur={(e) => handleGenreBlur(e.target.value)}
                    placeholder={t.book.genrePlaceholder}
                    aria-label={t.book.genreAriaLabel}
                    className="rounded-full border-none bg-surface-2 px-3 py-1 text-xs text-muted placeholder:text-muted/60"
                  />
                  <Select
                    value={languageChoice(book.language)}
                    onChange={handleLanguageChange}
                    ariaLabel={t.book.languageAriaLabel}
                    options={[
                      { value: "", label: t.flow.languageAuto },
                      { value: "fr", label: t.flow.languageFr },
                      { value: "en", label: t.flow.languageEn },
                    ]}
                  />
                  <input
                    key={`published-${book.published_at ?? ""}`}
                    type="date"
                    defaultValue={book.published_at ?? ""}
                    onChange={(e) => handlePublishedAtChange(e.target.value)}
                    aria-label={t.book.publishedAtLabel}
                    title={t.book.publishedAtLabel}
                    className="rounded-full border-none bg-surface-2 px-3 py-1 text-xs text-muted"
                  />
                </div>
              </details>
            </div>
          </header>

          <BookStepper status={book.status} failedStage={book.failed_stage} />

          {showCastingSection && (
            // Transition d'entrée seule (starting:, Tailwind v4).
            <section className="mt-6 rounded-2xl bg-surface p-5 shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)] transition-all duration-200 ease-out starting:translate-y-1 starting:opacity-0">
              <h2 className="mb-3 font-display text-xl font-medium tracking-tight">{t.book.casting}</h2>

              {castingLoading && !castingLoaded && (
                <p className="text-muted">{t.book.loadingCasting}</p>
              )}

              {mergeSuggestions.length > 0 && (
                <div className="mb-4 rounded-2xl border border-warning/30 bg-warning/10 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-sm font-semibold text-warning">
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
                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
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
                  {book.status === "ANALYZED" && (
                    <Button
                      variant="primary"
                      size="lg"
                      onClick={() => handleGenerateBook(false)}
                      disabled={!canGenerate}
                    >
                      {generating ? t.book.launching : t.flow.generateBook}
                    </Button>
                  )}
                </div>
              )}
            </section>
          )}

          <section className="mt-10">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-display text-2xl font-medium tracking-tight">
                {t.book.chaptersTitle(chapters.filter((c) => c.included).length)}
              </h2>
            </div>
            {chapters.length === 0 ? (
              <p className="text-muted">{t.book.noChaptersYet}</p>
            ) : (
              <ChapterList
                book={book}
                chapters={chapters}
                generatingPos={generatingPos}
                onGenerate={handleGenerateChapter}
                onToggleIncluded={handleToggleIncluded}
                onListen={(ch) => playChapter(ch)}
              />
            )}
          </section>
        </>
      )}
    </main>
  );
}
