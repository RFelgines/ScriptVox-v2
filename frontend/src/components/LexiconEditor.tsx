"use client";

import { useEffect, useState } from "react";
import {
  createLexiconEntry,
  deleteLexiconEntry,
  listLexicon,
  previewLexicon,
  type LexiconEntry,
} from "@/lib/api";
import Button from "@/components/ui/Button";
import { useT } from "@/lib/i18n/LanguageContext";

// Lexique de prononciation : sans `bookId`, les entrées globales ; avec, celles du livre
// (les globales sont listées aussi, marquées, et ne se suppriment que depuis Paramètres).
export default function LexiconEditor({ bookId }: { bookId?: number }) {
  const t = useT();
  const [entries, setEntries] = useState<LexiconEntry[]>([]);
  const [term, setTerm] = useState("");
  const [replacement, setReplacement] = useState("");
  const [wholeWord, setWholeWord] = useState(true);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [sample, setSample] = useState("");
  const [spoken, setSpoken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listLexicon(bookId)
      .then((e) => active && setEntries(e))
      .catch((e) => active && setError(String(e)));
    return () => {
      active = false;
    };
  }, [bookId]);

  async function add() {
    if (!term.trim()) return;
    try {
      const created = await createLexiconEntry({
        book_id: bookId ?? null, term: term.trim(), replacement,
        whole_word: wholeWord, case_sensitive: caseSensitive,
      });
      setEntries((prev) => [...prev, created].sort((a, b) => a.term.localeCompare(b.term)));
      setTerm("");
      setReplacement("");
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  async function remove(id: number) {
    try {
      await deleteLexiconEntry(id);
      setEntries((prev) => prev.filter((e) => e.id !== id));
    } catch (e) {
      setError(String(e));
    }
  }

  async function test() {
    try {
      setSpoken(await previewLexicon(sample, bookId));
    } catch (e) {
      setError(String(e));
    }
  }

  const input = "rounded-control border border-border bg-surface px-2 py-1 text-sm";
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">{t.production.lexiconHint}</p>
      {entries.length === 0 ? (
        <p className="text-sm text-muted">{t.production.lexiconEmpty}</p>
      ) : (
        <ul className="space-y-1.5">
          {entries.map((e) => {
            const global = bookId !== undefined && e.book_id === null;
            return (
              <li key={e.id} className="flex items-center gap-2 rounded-xl bg-surface-2/60 px-3 py-1.5 text-sm">
                <span className="font-medium">{e.term}</span>
                <span className="text-muted">→</span>
                <span className="flex-1">{e.replacement}</span>
                {global && (
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">
                    {t.production.lexiconGlobalBadge}
                  </span>
                )}
                {!global && (
                  <button onClick={() => remove(e.id)} className="text-muted hover:text-danger" aria-label="×">
                    ×
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input className={input} placeholder={t.production.lexiconTerm} value={term}
          onChange={(e) => setTerm(e.target.value)} />
        <input className={input} placeholder={t.production.lexiconReplacement} value={replacement}
          onChange={(e) => setReplacement(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
        <label className="flex items-center gap-1 text-xs text-muted">
          <input type="checkbox" checked={wholeWord} onChange={(e) => setWholeWord(e.target.checked)} />
          {t.production.lexiconWholeWord}
        </label>
        <label className="flex items-center gap-1 text-xs text-muted">
          <input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} />
          {t.production.lexiconCaseSensitive}
        </label>
        <Button size="sm" variant="primary" onClick={add} disabled={!term.trim()}>
          {t.production.lexiconAdd}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${input} min-w-64 flex-1`} placeholder={t.production.lexiconTestPlaceholder}
          value={sample} onChange={(e) => setSample(e.target.value)} onKeyDown={(e) => e.key === "Enter" && test()} />
        <Button size="sm" onClick={test} disabled={!sample.trim()}>{t.production.lexiconTest}</Button>
      </div>
      {spoken !== null && (
        <p className="text-sm">
          <span className="text-muted">{t.production.lexiconSpoken}</span> {spoken}
        </p>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
