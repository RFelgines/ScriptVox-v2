"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  BookSummary,
  ChapterSummary,
  getBook,
  listChapters,
  coverUrl,
  bookMp3Url,
} from "@/lib/api";
import CastingModal from "@/components/CastingModal";
import { usePlayer } from "@/components/player/PlayerProvider";

const STATUS_COLOR: Record<string, string> = {
  PENDING: "text-gray-400",
  PROCESSING: "text-blue-400",
  ANALYZED: "text-yellow-400",
  GENERATING: "text-orange-400",
  DONE: "text-green-400",
  FAILED: "text-red-400",
};

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

  const [book, setBook] = useState<BookSummary | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [castingOpen, setCastingOpen] = useState(false);
  const { play } = usePlayer();
  // Bumpé après une génération pour relancer le polling (l'effet s'arrête à
  // ANALYZED, qui n'est pas un état « actif »).
  const [reloadNonce, setReloadNonce] = useState(0);

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

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <Link href="/" className="text-sm text-gray-400 hover:text-gray-200">
        ← Bibliothèque
      </Link>

      {loading && !book && <p className="mt-6 text-gray-500">Chargement…</p>}

      {error && (
        <div className="mt-6 rounded border border-red-700 bg-red-900/40 p-4">
          <p className="font-semibold text-red-300">Erreur</p>
          <p className="mt-1 text-sm text-red-400">{error}</p>
        </div>
      )}

      {book && (
        <>
          <header className="mt-6 flex gap-6">
            <div className="aspect-[2/3] w-32 shrink-0 overflow-hidden rounded bg-gray-800">
              {book.cover_path ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={coverUrl(book.id)}
                  alt={`Couverture de ${book.title}`}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center p-2 text-center text-xs text-gray-600">
                  {book.title}
                </div>
              )}
            </div>

            <div className="flex-1">
              <h1 className="text-2xl font-bold">{book.title}</h1>
              {book.author && <p className="text-gray-400">{book.author}</p>}
              <p
                className={`mt-2 font-semibold ${STATUS_COLOR[book.status] ?? "text-gray-400"}`}
              >
                {book.status}
              </p>
              {book.progress > 0 && book.progress < 100 && (
                <div className="mt-2 h-2 w-full max-w-md overflow-hidden rounded bg-gray-800">
                  <div
                    className="h-full bg-orange-400"
                    style={{ width: `${book.progress}%` }}
                  />
                </div>
              )}
              {book.status === "FAILED" && book.error_message && (
                <p className="mt-2 text-sm text-red-400">{book.error_message}</p>
              )}
              {(book.status === "ANALYZED" ||
                book.status === "GENERATING" ||
                book.status === "DONE") && (
                <button
                  onClick={() => setCastingOpen(true)}
                  className="mt-3 rounded bg-gray-800 px-3 py-1.5 text-sm font-medium hover:bg-gray-700"
                >
                  Casting
                </button>
              )}
              {book.status === "DONE" && book.mp3_path && (
                <button
                  onClick={() => play({ title: book.title, src: bookMp3Url(book.id) })}
                  className="mt-3 ml-2 rounded bg-green-700 px-3 py-1.5 text-sm font-semibold hover:bg-green-600"
                >
                  ▶ Écouter
                </button>
              )}
            </div>
          </header>

          <section className="mt-8">
            <h2 className="mb-3 text-lg font-semibold">
              Chapitres ({chapters.length})
            </h2>
            {chapters.length === 0 ? (
              <p className="text-gray-500">Aucun chapitre pour l&apos;instant.</p>
            ) : (
              <ul className="space-y-2">
                {chapters.map((ch) => (
                  <li
                    key={ch.id}
                    className="flex items-center gap-3 rounded border border-gray-800 bg-gray-900 p-3"
                  >
                    <span className="w-8 text-right text-xs text-gray-500">
                      {ch.position}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm">{ch.title ?? `Chapitre ${ch.position}`}</p>
                      {ch.status === "FAILED" && ch.error_message && (
                        <p className="text-xs text-red-400">{ch.error_message}</p>
                      )}
                    </div>
                    <span
                      className={`text-xs font-semibold ${STATUS_COLOR[ch.status] ?? "text-gray-400"}`}
                    >
                      {ch.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {castingOpen && (
            <CastingModal
              bookId={book.id}
              bookStatus={book.status}
              onClose={() => setCastingOpen(false)}
              onGenerated={() => setReloadNonce((n) => n + 1)}
            />
          )}
        </>
      )}
    </main>
  );
}
