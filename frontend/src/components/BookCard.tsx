"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BookSummary, coverUrl, deleteBook } from "@/lib/api";
import { languageName, languageToFlag } from "@/lib/locale";
import StatusBadge from "@/components/ui/StatusBadge";
import { useFeedback } from "@/components/ui/Feedback";
import { useT } from "@/lib/i18n/LanguageContext";

export default function BookCard({
  book,
  onDeleted,
  availableLanguages,
}: {
  book: BookSummary;
  onDeleted: () => void;
  /** Codes de langue traités de bout en bout par le serveur (AppSettings.
   *  available_languages). Absent = on n'affiche aucun avertissement plutôt
   *  que d'en inventer un pendant le chargement des réglages. */
  availableLanguages?: string[];
}) {
  const t = useT();
  const { toast, confirm } = useFeedback();
  const [imgOk, setImgOk] = useState(true);
  // Suppression différée : la carte disparaît tout de suite, la suppression réelle n'a lieu
  // qu'après 6 s, laissant le temps de cliquer « Annuler » (audit 2026-09-25, UX-4).
  const [hidden, setHidden] = useState(false);
  const timerRef = useRef<number | null>(null);
  const commitRef = useRef<() => void>(() => {});
  const showCover = Boolean(book.cover_path) && imgOk;

  useEffect(() => {
    commitRef.current = () => {
      timerRef.current = null;
      deleteBook(book.id)
        .then(onDeleted)
        .catch((e) => {
          setHidden(false);
          toast(e instanceof Error ? e.message : String(e), { tone: "error" });
        });
    };
  });

  // Quitter la page pendant le délai = confirmer la suppression demandée.
  useEffect(
    () => () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        commitRef.current();
      }
    },
    [],
  );

  async function handleDelete() {
    const ok = await confirm({
      title: t.feedback.deleteConfirmTitle,
      message: book.title,
      danger: true,
    });
    if (!ok) return;
    setHidden(true);
    timerRef.current = window.setTimeout(() => commitRef.current(), 6000);
    toast(t.feedback.bookDeleted(book.title), {
      durationMs: 6000,
      action: {
        label: t.feedback.undo,
        onClick: () => {
          if (timerRef.current !== null) window.clearTimeout(timerRef.current);
          timerRef.current = null;
          setHidden(false);
        },
      },
    });
  }

  if (hidden) return null;

  return (
    <div className="group relative transition-transform duration-200 ease-out hover:-translate-y-1.5 hover:scale-[1.02]">
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

        {/* Langue du livre (dc:language de l'EPUB) : pastille ronde en coin de
            couverture. Le drapeau seul serait illisible pour qui ne le
            reconnaît pas, d'où le nom de la langue au survol et en aria-label. */}
        {book.language && languageToFlag(book.language) && (() => {
          // Langue non prise en charge : on affiche quand même le drapeau -- la
          // langue est un fait sur le livre, pas sur le moteur -- mais grisé et
          // explicité au survol. Le masquer rendrait la dégradation invisible :
          // l'utilisateur entendrait une phonétique française sans comprendre.
          const supported =
            !availableLanguages ||
            availableLanguages.includes(book.language.toLowerCase().split(/[-_]/)[0]);
          const label = supported
            ? languageName(book.language)
            : t.book.languageUnsupported(languageName(book.language));
          return (
            <span
              role="img"
              title={label}
              aria-label={label}
              className={`absolute top-2 right-2 flex h-7 w-7 items-center justify-center rounded-full text-sm leading-none backdrop-blur-sm ${
                supported
                  ? "bg-black/55"
                  : "bg-black/40 opacity-50 grayscale ring-1 ring-white/30"
              }`}
            >
              {languageToFlag(book.language)}
            </span>
          );
        })()}

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
        title={t.library.deleteAriaLabel}
        className="absolute top-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-full bg-black/40 text-xs text-white/80 backdrop-blur-sm transition-colors hover:bg-danger/80 hover:text-white disabled:opacity-50"
      >
        ✕
      </button>
    </div>
  );
}
