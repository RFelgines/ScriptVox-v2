"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listBooks, BookSummary } from "@/lib/api";
import UploadDropzone from "@/components/UploadDropzone";
import BookCard from "@/components/BookCard";
import Alert from "@/components/ui/Alert";

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
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold">Bibliothèque</h1>
        {!loading && !error && books.length > 0 && (
          <span className="text-sm text-muted">
            {books.length} livre{books.length > 1 ? "s" : ""}
          </span>
        )}
      </div>

      <UploadDropzone onUploaded={handleUploaded} />

      {loading && <p className="mt-6 text-muted">Connexion à l&apos;API…</p>}

      {error && (
        <Alert title="Impossible de joindre l'API" className="mt-6">
          <p className="text-sm text-red-400 mt-1">{error}</p>
          <p className="text-sm text-muted mt-2">
            Vérifiez que l&apos;API tourne sur{" "}
            <code className="bg-surface-2 px-1 rounded">
              {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
            </code>
          </p>
        </Alert>
      )}

      {!loading && !error && books.length === 0 && (
        <p className="mt-6 text-muted">Aucun livre. Glissez un EPUB ci-dessus.</p>
      )}

      {books.length > 0 && (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {books.map((book) => (
            <BookCard key={book.id} book={book} onDeleted={refresh} />
          ))}
        </div>
      )}
    </main>
  );
}
