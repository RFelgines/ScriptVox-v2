"use client";

import { useEffect, useState } from "react";
import { listBooks, BookSummary } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  PENDING: "text-gray-400",
  PROCESSING: "text-blue-400",
  ANALYZED: "text-yellow-400",
  GENERATING: "text-orange-400",
  DONE: "text-green-400",
  FAILED: "text-red-400",
};

export default function Home() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listBooks()
      .then(setBooks)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <h1 className="text-3xl font-bold mb-2">ScriptVox</h1>
      <p className="text-gray-400 mb-8">EPUB → audiobook multi-voix</p>

      {loading && <p className="text-gray-500">Connexion à l&apos;API…</p>}

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded p-4 mb-6">
          <p className="font-semibold text-red-300">Impossible de joindre l&apos;API</p>
          <p className="text-sm text-red-400 mt-1">{error}</p>
          <p className="text-sm text-gray-400 mt-2">
            Vérifiez que l&apos;API tourne sur{" "}
            <code className="bg-gray-800 px-1 rounded">
              {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
            </code>
          </p>
        </div>
      )}

      {!loading && !error && books.length === 0 && (
        <p className="text-gray-500">Aucun livre. Uploadez un EPUB via POST /books.</p>
      )}

      {books.length > 0 && (
        <ul className="space-y-3">
          {books.map((book) => (
            <li
              key={book.id}
              className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center gap-4"
            >
              <div className="flex-1">
                <p className="font-medium">{book.title}</p>
                <p className="text-xs text-gray-500">
                  #{book.id} · {new Date(book.created_at).toLocaleString()}
                </p>
              </div>
              <div className="text-right">
                <span
                  className={`text-sm font-semibold ${STATUS_COLOR[book.status] ?? "text-gray-400"}`}
                >
                  {book.status}
                </span>
                {book.progress > 0 && book.progress < 100 && (
                  <p className="text-xs text-gray-500">{book.progress.toFixed(0)} %</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
