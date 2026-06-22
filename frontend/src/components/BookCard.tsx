"use client";

import { useState } from "react";
import Link from "next/link";
import { BookSummary, coverUrl, deleteBook } from "@/lib/api";
import StatusBadge from "@/components/ui/StatusBadge";

export default function BookCard({
  book,
  onDeleted,
}: {
  book: BookSummary;
  onDeleted: () => void;
}) {
  const [imgOk, setImgOk] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const showCover = Boolean(book.cover_path) && imgOk;

  function handleDelete() {
    if (!window.confirm(`Supprimer « ${book.title} » ?`)) return;
    setDeleting(true);
    deleteBook(book.id)
      .then(onDeleted)
      .catch((e) => {
        window.alert(String(e));
        setDeleting(false);
      });
  }

  return (
    <div className="relative">
      <Link
        href={`/books/${book.id}`}
        className="flex flex-col overflow-hidden rounded-lg border border-gray-800 bg-gray-900 transition-colors hover:border-gray-600"
      >
        <div className="aspect-[2/3] bg-gray-800">
          {showCover ? (
            // <img> natif : la couverture est servie par l'API (host distant),
            // ce qui éviterait sinon de configurer `images.remotePatterns`.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={coverUrl(book.id)}
              alt={`Couverture de ${book.title}`}
              className="h-full w-full object-cover"
              onError={() => setImgOk(false)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center p-4 text-center text-sm text-gray-600">
              {book.title}
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-2 p-3">
          <p className="line-clamp-2 text-sm font-medium" title={book.title}>
            {book.title}
          </p>
          <div className="mt-auto flex items-center justify-between">
            <span className="text-xs text-gray-500">#{book.id}</span>
            <StatusBadge status={book.status} className="text-xs" />
          </div>
          {book.progress > 0 && book.progress < 100 && (
            <div className="h-1 w-full overflow-hidden rounded bg-gray-800">
              <div
                className="h-full bg-orange-400"
                style={{ width: `${book.progress}%` }}
              />
            </div>
          )}
        </div>
      </Link>

      <button
        onClick={handleDelete}
        disabled={deleting}
        title="Supprimer"
        className="absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded-full bg-gray-950/80 text-xs text-gray-400 hover:bg-red-900 hover:text-red-200 disabled:opacity-50"
      >
        {deleting ? "…" : "✕"}
      </button>
    </div>
  );
}
