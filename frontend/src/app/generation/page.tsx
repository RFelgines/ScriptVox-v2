"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { QueueItem, coverUrl, getQueue, patchChapterPriority, stopChapter } from "@/lib/api";
import Alert from "@/components/ui/Alert";
import Skeleton from "@/components/ui/Skeleton";
import Button from "@/components/ui/Button";
import StatusBadge from "@/components/ui/StatusBadge";
import { useT } from "@/lib/i18n/LanguageContext";
import type { Dictionary } from "@/lib/i18n/translations";

const POLL_MS = 3000;

function chapterLabel(item: QueueItem, t: Dictionary): string {
  return item.title ? item.title : t.generation.chapterFallback(item.position);
}

// Vignette de couverture — même repli que BookCard.tsx (initiale du titre si
// pas de couverture ou 404), mais en petit format pour tenir à côté du texte.
function CoverThumb({ bookId, title, t }: { bookId: number; title: string; t: Dictionary }) {
  const [imgOk, setImgOk] = useState(true);
  return (
    <div className="h-14 w-10 shrink-0 overflow-hidden rounded-control bg-surface-2">
      {imgOk ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={coverUrl(bookId)}
          alt={t.generation.coverAlt(title)}
          className="h-full w-full object-cover"
          onError={() => setImgOk(false)}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-xs font-medium text-muted">
          {title.charAt(0).toUpperCase()}
        </div>
      )}
    </div>
  );
}

export default function GenerationPage() {
  const t = useT();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stoppingId, setStoppingId] = useState<number | null>(null);
  const [movingId, setMovingId] = useState<number | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [draggedId, setDraggedId] = useState<number | null>(null);
  const [dragOverId, setDragOverId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    // setTimeout récursif (pas setInterval) : la file peut changer d'ailleurs dans
    // l'app (une génération lancée depuis une page livre) — on poll en continu,
    // il n'y a pas d'état "terminé" pour cette page (contrairement à un livre).
    function tick() {
      getQueue()
        .then((items) => {
          if (!active) return;
          setQueue(items);
          setError(null);
          timer = setTimeout(tick, POLL_MS);
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
  }, [reloadNonce]);

  function handleStop(item: QueueItem) {
    setStoppingId(item.chapter_id);
    stopChapter(item.book_id, item.position)
      .then(() => setReloadNonce((n) => n + 1))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setStoppingId(null));
  }

  // Ré-échanger la valeur brute de priority ne suffit pas : tous les chapitres
  // partagent priority=0 par défaut, donc échanger deux valeurs égales est un
  // no-op silencieux au premier déplacement. On ré-attribue plutôt un rang
  // strictement décroissant à TOUTE la liste affichée après le déplacement
  // (n'envoie que les PATCH pour les entrées dont le rang change réellement) —
  // garantit un ordre total dès le premier clic, quel que soit l'état de départ.
  // Partagé entre les flèches ↑/↓ et le glisser-déposer, seule la façon de
  // produire `reordered` diffère entre les deux.
  function applyReorder(reordered: QueueItem[], movedChapterId: number) {
    const n = reordered.length;
    const updates = reordered
      .map((item, i) => ({ item, rank: n - i }))
      .filter(({ item, rank }) => item.priority !== rank);

    setMovingId(movedChapterId);
    Promise.all(
      updates.map(({ item, rank }) => patchChapterPriority(item.book_id, item.position, rank)),
    )
      .then(() => setReloadNonce((n) => n + 1))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setMovingId(null));
  }

  function movePending(pending: QueueItem[], index: number, direction: -1 | 1) {
    const otherIndex = index + direction;
    if (otherIndex < 0 || otherIndex >= pending.length) return;
    const reordered = [...pending];
    [reordered[index], reordered[otherIndex]] = [reordered[otherIndex], reordered[index]];
    applyReorder(reordered, pending[index].chapter_id);
  }

  function handleDrop(pending: QueueItem[], targetItem: QueueItem) {
    setDragOverId(null);
    if (draggedId === null || draggedId === targetItem.chapter_id) {
      setDraggedId(null);
      return;
    }
    const fromIndex = pending.findIndex((i) => i.chapter_id === draggedId);
    const toIndex = pending.findIndex((i) => i.chapter_id === targetItem.chapter_id);
    if (fromIndex === -1 || toIndex === -1) {
      setDraggedId(null);
      return;
    }
    const reordered = [...pending];
    const [moved] = reordered.splice(fromIndex, 1);
    reordered.splice(toIndex, 0, moved);
    applyReorder(reordered, moved.chapter_id);
    setDraggedId(null);
  }

  const generating = queue.find((item) => item.status === "GENERATING") ?? null;
  const pending = queue.filter((item) => item.status === "PENDING");

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-3xl font-bold text-foreground">{t.generation.title}</h1>
      <p className="mt-1 text-sm text-muted">
        {t.generation.subtitle}
      </p>

      {error && (
        <Alert title={t.generation.errorTitle} className="mt-6">
          <p className="text-sm text-danger">{error}</p>
        </Alert>
      )}

      {loading ? (
        <div className="mt-8 space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : (
        <>
          <section className="mt-8">
            <h2 className="text-xl font-semibold text-foreground">
              {t.generation.inProgress}
            </h2>
            {generating ? (
              <div className="mt-3 flex items-center justify-between rounded-card border border-border bg-surface p-4">
                <div className="flex items-center gap-3">
                  <CoverThumb bookId={generating.book_id} title={generating.book_title} t={t} />
                  <div>
                    <Link
                      href={`/books/${generating.book_id}`}
                      className="font-medium text-foreground hover:underline"
                    >
                      {generating.book_title}
                    </Link>
                    <p className="text-sm text-muted">{chapterLabel(generating, t)}</p>
                    <StatusBadge status={generating.status} className="mt-1" />
                  </div>
                </div>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={stoppingId === generating.chapter_id}
                  onClick={() => handleStop(generating)}
                >
                  {stoppingId === generating.chapter_id ? t.generation.stopping : t.generation.stop}
                </Button>
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted">{t.generation.noneInProgress}</p>
            )}
          </section>

          <section className="mt-8">
            <h2 className="text-xl font-semibold text-foreground">
              {t.generation.pending(pending.length)}
            </h2>
            {pending.length === 0 ? (
              <p className="mt-3 text-sm text-muted">{t.generation.queueEmpty}</p>
            ) : (
              <ol className="mt-3 space-y-2">
                {pending.map((item, index) => (
                  <li
                    key={item.chapter_id}
                    draggable={movingId === null}
                    onDragStart={() => setDraggedId(item.chapter_id)}
                    onDragOver={(e) => {
                      e.preventDefault();
                      if (dragOverId !== item.chapter_id) setDragOverId(item.chapter_id);
                    }}
                    onDragLeave={() => {
                      if (dragOverId === item.chapter_id) setDragOverId(null);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      handleDrop(pending, item);
                    }}
                    onDragEnd={() => {
                      setDraggedId(null);
                      setDragOverId(null);
                    }}
                    className={`flex items-center justify-between gap-3 rounded-card border p-3 transition-colors ${
                      dragOverId === item.chapter_id && draggedId !== item.chapter_id
                        ? "border-primary bg-surface-2"
                        : "border-border bg-surface"
                    } ${draggedId === item.chapter_id ? "opacity-40" : ""} ${
                      movingId === null ? "cursor-grab active:cursor-grabbing" : ""
                    }`}
                  >
                    <span
                      className="shrink-0 select-none text-muted/50"
                      aria-hidden="true"
                      title={t.generation.dragToReorder}
                    >
                      <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4">
                        <circle cx="5" cy="4" r="1.3" />
                        <circle cx="11" cy="4" r="1.3" />
                        <circle cx="5" cy="8" r="1.3" />
                        <circle cx="11" cy="8" r="1.3" />
                        <circle cx="5" cy="12" r="1.3" />
                        <circle cx="11" cy="12" r="1.3" />
                      </svg>
                    </span>
                    <CoverThumb bookId={item.book_id} title={item.book_title} t={t} />
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/books/${item.book_id}`}
                        className="font-medium text-foreground hover:underline"
                      >
                        {item.book_title}
                      </Link>
                      <p className="truncate text-sm text-muted">{chapterLabel(item, t)}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={index === 0 || movingId !== null}
                        onClick={() => movePending(pending, index, -1)}
                        aria-label={t.generation.moveUp}
                      >
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                          <path d="M8 12.5V3.5M4 7l4-4 4 4" />
                        </svg>
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={index === pending.length - 1 || movingId !== null}
                        onClick={() => movePending(pending, index, 1)}
                        aria-label={t.generation.moveDown}
                      >
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                          <path d="M8 3.5v9M4 9l4 4 4-4" />
                        </svg>
                      </Button>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </main>
  );
}
