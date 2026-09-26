"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  listBooks,
  uploadBook,
  BookSummary,
  BookStatus,
  AppSettings,
  getAppSettings,
} from "@/lib/api";
import UploadDropzone from "@/components/UploadDropzone";
import BookCard from "@/components/BookCard";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";
import { useFeedback } from "@/components/ui/Feedback";
import { formatClock, listResumes, type ResumePoint } from "@/lib/resume";
import { useT } from "@/lib/i18n/LanguageContext";

const DEFAULT_PROVIDER_KEY = "__default__";

type SortKey =
  | "NONE"
  | "TITLE_ASC"
  | "ADDED_DESC"
  | "ADDED_ASC"
  | "PUBLISHED_DESC"
  | "PUBLISHED_ASC";

function sortBooks(books: BookSummary[], sortKey: SortKey): BookSummary[] {
  const sorted = [...books];
  switch (sortKey) {
    case "TITLE_ASC":
      return sorted.sort((a, b) => a.title.localeCompare(b.title));
    case "ADDED_DESC":
      return sorted.sort((a, b) => b.created_at.localeCompare(a.created_at));
    case "ADDED_ASC":
      return sorted.sort((a, b) => a.created_at.localeCompare(b.created_at));
    case "PUBLISHED_DESC":
      return sorted.sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
    case "PUBLISHED_ASC":
      return sorted.sort((a, b) =>
        (a.published_at ?? "9999").localeCompare(b.published_at ?? "9999"),
      );
    default:
      return sorted;
  }
}

const SELECT_CLASS =
  "rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted";

export default function Home() {
  const router = useRouter();
  const t = useT();
  const { toast } = useFeedback();
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null);
  const [statusFilter, setStatusFilter] = useState<BookStatus | "ALL">("ALL");
  const [providerFilter, setProviderFilter] = useState<string>("ALL");
  const [genreFilter, setGenreFilter] = useState<string>("ALL");
  const [authorFilter, setAuthorFilter] = useState<string>("ALL");
  const [languageFilter, setLanguageFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("NONE");
  const [resumes, setResumes] = useState<{ bookId: number; point: ResumePoint }[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importRef = useRef<(file: File) => void>(() => {});

  function refresh() {
    return listBooks()
      .then((data) => {
        setBooks(data);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  // Après l'upload, on navigue directement sur le livre : l'analyse démarre et le casting
  // s'ouvre de lui-même dès qu'elle est terminée (cf. books/[id]/page.tsx).
  function handleUploaded(book: BookSummary) {
    router.push(`/books/${book.id}`);
  }

  async function importFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".epub")) {
      toast(t.upload.invalidFile, { tone: "error" });
      return;
    }
    setUploading(true);
    try {
      handleUploaded(await uploadBook(file));
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), { tone: "error" });
    } finally {
      setUploading(false);
    }
  }

  useEffect(() => {
    importRef.current = (file: File) => {
      void importFile(file);
    };
  });

  useEffect(() => {
    refresh();
    getAppSettings().then(setAppSettings).catch(() => {});
    // localStorage n'existe pas côté serveur : lu après l'hydratation.
    Promise.resolve().then(() => setResumes(listResumes()));
  }, []);

  // Un livre est en cours de traitement : la liste se rafraîchit (10 s), sinon elle reste figée.
  const hasActiveBook = books.some(
    (b) => b.status === "PENDING" || b.status === "PROCESSING" || b.status === "GENERATING",
  );
  useEffect(() => {
    if (!hasActiveBook) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 10000);
    return () => window.clearInterval(id);
  }, [hasActiveBook]);

  // Dépôt d'un fichier n'importe où sur la page (calque plein écran pendant le survol).
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth += 1;
      setDragging(true);
    };
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const onOver = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      const file = e.dataTransfer?.files?.[0];
      if (file) importRef.current(file);
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDrop);
    };
  }, []);

  const genreOptions = Array.from(
    new Set(books.map((b) => b.genre).filter((g): g is string => !!g)),
  ).sort();
  const authorOptions = Array.from(
    new Set(books.map((b) => b.author).filter((a): a is string => !!a)),
  ).sort();
  const languageOptions = Array.from(
    new Set(books.map((b) => b.language).filter((l): l is string => !!l)),
  ).sort();

  const searchQuery = search.trim().toLowerCase();

  const filteredBooks = books
    .filter((b) => statusFilter === "ALL" || b.status === statusFilter)
    .filter((b) => {
      if (providerFilter === "ALL") return true;
      if (providerFilter === DEFAULT_PROVIDER_KEY) return b.tts_provider === null;
      return b.tts_provider === providerFilter;
    })
    .filter((b) => genreFilter === "ALL" || b.genre === genreFilter)
    .filter((b) => authorFilter === "ALL" || b.author === authorFilter)
    .filter((b) => languageFilter === "ALL" || b.language === languageFilter)
    .filter(
      (b) =>
        !searchQuery ||
        b.title.toLowerCase().includes(searchQuery) ||
        (b.author ?? "").toLowerCase().includes(searchQuery),
    );

  const visibleBooks = sortBooks(filteredBooks, sortKey);

  // Filtres regroupés dans un menu : la recherche reste seule visible (bibliothèque personnelle).
  const activeFilterCount = [
    statusFilter !== "ALL",
    providerFilter !== "ALL",
    genreFilter !== "ALL",
    authorFilter !== "ALL",
    languageFilter !== "ALL",
    sortKey !== "NONE",
  ].filter(Boolean).length;
  const filtersActive = activeFilterCount > 0 || searchQuery !== "";

  function resetFilters() {
    setStatusFilter("ALL");
    setProviderFilter("ALL");
    setGenreFilter("ALL");
    setAuthorFilter("ALL");
    setLanguageFilter("ALL");
    setSortKey("NONE");
    setSearch("");
  }

  const bookById = new Map(books.map((b) => [b.id, b]));
  const resumeCards = resumes
    .map((r) => ({ book: bookById.get(r.bookId), point: r.point }))
    .filter(
      (r): r is { book: BookSummary; point: ResumePoint } =>
        r.book !== undefined && r.book.status === "DONE",
    )
    .slice(0, 3);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      {/* Calque de dépôt : apparaît dès qu'un fichier survole la fenêtre. */}
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-[80] flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="rounded-card border-2 border-dashed border-primary px-10 py-8 font-display text-xl">
            {t.library2.dropOverlay}
          </div>
        </div>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept=".epub"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) importRef.current(file);
          e.target.value = "";
        }}
      />

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-3xl font-medium tracking-tight">{t.library.title}</h1>
          {!loading && !error && books.length > 0 && (
            <span className="text-sm text-muted">
              {t.library.bookCount(visibleBooks.length)}
              {filtersActive && t.library.filteredOf(books.length)}
            </span>
          )}
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="rounded-control bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {uploading ? t.upload.uploading : `+ ${t.library2.importEpub}`}
        </button>
      </div>

      {!loading && !error && books.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t.library.searchPlaceholder}
            aria-label={t.library.searchAriaLabel}
            className="min-w-48 flex-1 rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm placeholder:text-muted"
          />
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-control border border-border bg-surface-2 px-3 py-1.5 text-sm text-muted hover:text-foreground [&::-webkit-details-marker]:hidden">
              {activeFilterCount > 0 ? t.library2.filtersActive(activeFilterCount) : t.library2.filters}
            </summary>
            <div className="absolute right-0 z-20 mt-1 flex w-72 flex-col gap-2 rounded-2xl border border-border bg-surface p-3 shadow-lg">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as BookStatus | "ALL")}
                aria-label={t.library.filterStatusAriaLabel}
                className={SELECT_CLASS}
              >
                <option value="ALL">{t.library.allStatuses}</option>
                {(Object.keys(t.library.statusLabels) as BookStatus[]).map((s) => (
                  <option key={s} value={s}>
                    {t.library.statusLabels[s]}
                  </option>
                ))}
              </select>
              {appSettings && (
                <select
                  value={providerFilter}
                  onChange={(e) => setProviderFilter(e.target.value)}
                  aria-label={t.library.filterProviderAriaLabel}
                  className={SELECT_CLASS}
                >
                  <option value="ALL">{t.library.allProviders}</option>
                  <option value={DEFAULT_PROVIDER_KEY}>
                    {t.library.defaultProvider(appSettings.default_tts_provider)}
                  </option>
                  {appSettings.available_tts_providers.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              )}
              {genreOptions.length > 0 && (
                <select
                  value={genreFilter}
                  onChange={(e) => setGenreFilter(e.target.value)}
                  aria-label={t.library.filterGenreAriaLabel}
                  className={SELECT_CLASS}
                >
                  <option value="ALL">{t.library.allGenres}</option>
                  {genreOptions.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              )}
              {authorOptions.length > 0 && (
                <select
                  value={authorFilter}
                  onChange={(e) => setAuthorFilter(e.target.value)}
                  aria-label={t.library.filterAuthorAriaLabel}
                  className={SELECT_CLASS}
                >
                  <option value="ALL">{t.library.allAuthors}</option>
                  {authorOptions.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              )}
              {languageOptions.length > 0 && (
                <select
                  value={languageFilter}
                  onChange={(e) => setLanguageFilter(e.target.value)}
                  aria-label={t.library.filterLanguageAriaLabel}
                  className={SELECT_CLASS}
                >
                  <option value="ALL">{t.library.allLanguages}</option>
                  {languageOptions.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
              )}
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                aria-label={t.library.sortAriaLabel}
                className={SELECT_CLASS}
              >
                {(Object.keys(t.library.sortLabels) as SortKey[]).map((k) => (
                  <option key={k} value={k}>
                    {t.library.sortLabels[k]}
                  </option>
                ))}
              </select>
              {filtersActive && (
                <button
                  onClick={resetFilters}
                  className="self-start text-xs text-muted underline underline-offset-2 hover:text-foreground"
                >
                  {t.library2.resetFilters}
                </button>
              )}
            </div>
          </details>
        </div>
      )}

      {/* Reprendre l'écoute : livres terminés avec une position enregistrée. */}
      {resumeCards.length > 0 && !filtersActive && (
        <section className="mb-8">
          <h2 className="mb-2 text-sm font-medium text-muted">{t.library2.continueListening}</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {resumeCards.map(({ book, point }) => (
              <Link
                key={book.id}
                href={`/books/${book.id}`}
                className="flex items-center gap-3 rounded-2xl bg-surface p-3 transition-colors hover:bg-surface-2"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-display text-sm font-medium">{book.title}</span>
                  <span className="block truncate text-xs text-muted">
                    {t.book.chapterFallback(point.chapterPosition)} · {formatClock(point.time)}
                  </span>
                </span>
                <span className="shrink-0 text-muted" aria-hidden="true">
                  ▶
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Zone de dépôt visible seulement quand la bibliothèque est vide. */}
      {!loading && !error && books.length === 0 && <UploadDropzone onUploaded={handleUploaded} />}

      {loading && (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="flex flex-col overflow-hidden rounded-card border border-border bg-surface">
              <Skeleton className="aspect-[2/3] rounded-none" />
              <div className="flex flex-col gap-2 p-3">
                <Skeleton className="h-3 w-full rounded" />
                <Skeleton className="h-3 w-2/3 rounded" />
                <Skeleton className="mt-2 h-5 w-16 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <Alert title={t.library.apiUnreachableTitle} className="mt-6">
          <p className="text-sm text-danger mt-1">{error}</p>
          <p className="text-sm text-muted mt-2">
            {t.library.apiUnreachableHint}{" "}
            <code className="bg-surface-2 px-1 rounded">
              {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
            </code>
          </p>
        </Alert>
      )}

      {!loading && !error && books.length > 0 && visibleBooks.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-3 text-center text-muted">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          <p className="text-base font-medium text-foreground">{t.library.noMatchTitle}</p>
          <p className="text-sm">{t.library.noMatchHint}</p>
        </div>
      )}

      {visibleBooks.length > 0 && (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {visibleBooks.map((book) => (
            <BookCard key={book.id} book={book} onDeleted={refresh} />
          ))}
        </div>
      )}
    </main>
  );
}
