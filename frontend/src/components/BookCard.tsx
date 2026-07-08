"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { BookSummary, coverUrl, deleteBook } from "@/lib/api";
import StatusBadge from "@/components/ui/StatusBadge";
import { useT } from "@/lib/i18n/LanguageContext";

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
};

export default function BookCard({
  book,
  onDeleted,
}: {
  book: BookSummary;
  onDeleted: () => void;
}) {
  const t = useT();
  const [imgOk, setImgOk] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const showCover = Boolean(book.cover_path) && imgOk;

  function handleDelete() {
    if (!window.confirm(t.library.deleteConfirm(book.title))) return;
    setDeleting(true);
    deleteBook(book.id)
      .then(onDeleted)
      .catch((e) => {
        window.alert(String(e));
        setDeleting(false);
      });
  }

  return (
    <motion.div
      variants={cardVariants}
      whileHover={{ y: -6, scale: 1.02 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
      className="group relative"
    >
      <Link
        href={`/books/${book.id}`}
        // Tuile pleine bordure/panneau supprimés : la couverture remplit toute
        // la carte, titre/auteur/statut incrustés en bas (façon Audible/Netflix).
        // Halo clair au lieu d'une ombre noire (invisible sur fond #1a1917).
        className="relative block aspect-[2/3] overflow-hidden rounded-2xl bg-surface-2 shadow-[0_1px_2px_rgba(0,0,0,0.4),0_0_0_1px_rgba(245,243,241,0.03)] transition-shadow duration-300 hover:shadow-[0_24px_48px_-16px_rgba(0,0,0,0.75),0_0_32px_rgba(245,243,241,0.12)]"
      >
        {showCover ? (
          // <img> natif : la couverture est servie par l'API (host distant),
          // ce qui éviterait sinon de configurer `images.remotePatterns`.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={coverUrl(book.id)}
            alt={t.book.coverAlt(book.title)}
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.06]"
            onError={() => setImgOk(false)}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-muted/40">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
          </div>
        )}

        {/* Scrim fixe (indépendant du thème clair/sombre) -- lisibilité du
            texte incrusté garantie quelle que soit la couverture. */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/10 to-transparent" />

        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-1.5 p-3.5">
          <p
            className="line-clamp-2 font-display text-base leading-tight font-medium text-white"
            title={book.title}
          >
            {book.title}
          </p>
          {book.author && (
            <p className="truncate text-xs text-white/70" title={book.author}>
              {book.author}
            </p>
          )}
          <StatusBadge status={book.status} tone="on-image" className="text-xs" />
        </div>

        {book.progress > 0 && book.progress < 100 && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-black/30">
            <div className="h-full bg-primary" style={{ width: `${book.progress}%` }} />
          </div>
        )}
      </Link>

      <button
        onClick={handleDelete}
        disabled={deleting}
        title={t.library.deleteAriaLabel}
        className="absolute top-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-full bg-black/40 text-xs text-white/80 backdrop-blur-sm transition-colors hover:bg-danger/80 hover:text-white disabled:opacity-50"
      >
        {deleting ? "…" : "✕"}
      </button>
    </motion.div>
  );
}
