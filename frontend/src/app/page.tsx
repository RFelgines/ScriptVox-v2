"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listBooks, BookSummary, BookStatus, AppSettings, getAppSettings } from "@/lib/api";
import UploadDropzone from "@/components/UploadDropzone";
import BookCard from "@/components/BookCard";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";

const STATUS_LABELS: Record<BookStatus, string> = {
  PENDING: "En attente",
  PROCESSING: "Analyse en cours",
  ANALYZED: "Analysé",
  GENERATING: "Génération en cours",
  DONE: "Terminé",
  FAILED: "Échec",
};

const DEFAULT_PROVIDER_KEY = "__default__";

type SortKey =
  | "NONE"
  | "TITLE_ASC"
  | "ADDED_DESC"
  | "ADDED_ASC"
  | "PUBLISHED_DESC"
  | "PUBLISHED_ASC";

const SORT_LABELS: Record<SortKey, string> = {
  NONE: "Tri par défaut",
  TITLE_ASC: "Titre (A→Z)",
  ADDED_DESC: "Date d'ajout (récent d'abord)",
  ADDED_ASC: "Date d'ajout (ancien d'abord)",
  PUBLISHED_DESC: "Date de publication (récent d'abord)",
  PUBLISHED_ASC: "Date de publication (ancien d'abord)",
};

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

export default function Home() {
  const router = useRouter();
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

  function refresh() {
    return listBooks()
      .then((data) => {
        setBooks(data);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  // Après l'upload, on navigue directement sur le livre avec ?casting=auto :
  // la modale de casting s'ouvrira d'elle-même dès que l'analyse atteint ANALYZED
  // (cf. books/[id]/page.tsx), servant de confirmation "tout valider ou ajuster".
  function handleUploaded(book: BookSummary) {
    router.push(`/books/${book.id}?casting=auto`);
  }

  useEffect(() => {
    refresh();
    getAppSettings().then(setAppSettings).catch(() => {});
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

  const filtersActive =
    statusFilter !== "ALL" ||
    providerFilter !== "ALL" ||
    genreFilter !== "ALL" ||
    authorFilter !== "ALL" ||
    languageFilter !== "ALL" ||
    searchQuery !== "";

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold">Bibliothèque</h1>
        {!loading && !error && books.length > 0 && (
          <span className="text-sm text-muted">
            {visibleBooks.length} livre{visibleBooks.length > 1 ? "s" : ""}
            {filtersActive && ` sur ${books.length}`}
          </span>
        )}
      </div>

      {!loading && !error && books.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un titre ou un auteur…"
            aria-label="Rechercher un livre"
            className="min-w-48 flex-1 rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm placeholder:text-muted"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as BookStatus | "ALL")}
            aria-label="Filtrer par statut"
            className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
          >
            <option value="ALL">Tous statuts</option>
            {(Object.keys(STATUS_LABELS) as BookStatus[]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
          {appSettings && (
            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              aria-label="Filtrer par modèle TTS"
              className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
            >
              <option value="ALL">Tous moteurs TTS</option>
              <option value={DEFAULT_PROVIDER_KEY}>
                Par défaut ({appSettings.default_tts_provider})
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
              aria-label="Filtrer par genre"
              className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
            >
              <option value="ALL">Tous genres</option>
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
              aria-label="Filtrer par auteur"
              className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
            >
              <option value="ALL">Tous auteurs</option>
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
              aria-label="Filtrer par langue"
              className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
            >
              <option value="ALL">Toutes langues</option>
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
            aria-label="Trier par"
            className="rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-muted"
          >
            {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
      )}

      <UploadDropzone onUploaded={handleUploaded} />

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
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-500 mt-1">{error}</p>
          <p className="text-sm text-muted mt-2">
            Vérifiez que l&apos;API tourne sur{" "}
            <code className="bg-surface-2 px-1 rounded">
              {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
            </code>
          </p>
        </Alert>
      )}

      {!loading && !error && books.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-3 text-center text-muted">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <p className="text-base font-medium text-foreground">Bibliothèque vide</p>
          <p className="text-sm">Glissez un fichier EPUB ci-dessus pour commencer.</p>
        </div>
      )}

      {!loading && !error && books.length > 0 && visibleBooks.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-3 text-center text-muted">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          <p className="text-base font-medium text-foreground">Aucun livre ne correspond</p>
          <p className="text-sm">Essayez d&apos;élargir les filtres ci-dessus.</p>
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
