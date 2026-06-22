"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listBooks, BookSummary } from "@/lib/api";
import UploadDropzone from "@/components/UploadDropzone";
import BookCard from "@/components/BookCard";

export default function Home() {
  const router = useRouter();
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
  }, []);

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <h1 className="text-3xl font-bold mb-2">ScriptVox</h1>
      <p className="text-gray-400 mb-8">EPUB → audiobook multi-voix</p>

      <UploadDropzone onUploaded={handleUploaded} />

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
        <p className="text-gray-500">Aucun livre. Glissez un EPUB ci-dessus.</p>
      )}

      {books.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {books.map((book) => (
            <BookCard key={book.id} book={book} onDeleted={refresh} />
          ))}
        </div>
      )}
    </main>
  );
}
