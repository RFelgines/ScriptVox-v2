"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookSummary, listBooks } from "@/lib/api";
import Alert from "@/components/ui/Alert";
import StatusBadge from "@/components/ui/StatusBadge";

export default function CastingPickerPage() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listBooks()
      .then((data) => {
        setBooks(data);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-2xl font-bold">Casting</h1>
      <p className="mt-2 text-gray-400">Choisissez un livre pour gérer son casting de voix.</p>

      {loading && <p className="mt-6 text-gray-500">Chargement…</p>}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-400">{error}</p>
        </Alert>
      )}

      {!loading && !error && books.length === 0 && (
        <p className="mt-6 text-gray-500">
          Aucun livre. Allez dans la Bibliothèque pour en ajouter un.
        </p>
      )}

      {books.length > 0 && (
        <ul className="mt-6 space-y-2">
          {books.map((book) => (
            <li key={book.id}>
              <Link
                href={`/casting/${book.id}`}
                className="flex items-center justify-between gap-3 rounded border border-gray-800 bg-gray-900 p-3 transition-colors hover:border-gray-600"
              >
                <span className="truncate text-sm font-medium">{book.title}</span>
                <StatusBadge status={book.status} className="shrink-0 text-xs" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
