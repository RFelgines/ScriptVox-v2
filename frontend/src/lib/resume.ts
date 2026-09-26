// Reprise de lecture : dernière position par livre, dans localStorage (audit 2026-09-25, UX-3).
// Local au navigateur, jamais envoyé au serveur.

export interface ResumePoint {
  chapterPosition: number;
  time: number; // secondes
  updatedAt: number; // ms epoch
}

const PREFIX = "scriptvox:resume:";

export function saveResume(bookId: number, point: ResumePoint): void {
  try {
    localStorage.setItem(PREFIX + bookId, JSON.stringify(point));
  } catch {
    // stockage indisponible ou plein : la reprise est un confort, jamais bloquante
  }
}

export function getResume(bookId: number): ResumePoint | null {
  try {
    const raw = localStorage.getItem(PREFIX + bookId);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<ResumePoint>;
    if (
      typeof value.chapterPosition !== "number" ||
      typeof value.time !== "number" ||
      typeof value.updatedAt !== "number"
    ) {
      return null;
    }
    return { chapterPosition: value.chapterPosition, time: value.time, updatedAt: value.updatedAt };
  } catch {
    return null;
  }
}

export function listResumes(): { bookId: number; point: ResumePoint }[] {
  const out: { bookId: number; point: ResumePoint }[] = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(PREFIX)) continue;
      const bookId = Number(key.slice(PREFIX.length));
      const point = getResume(bookId);
      if (Number.isFinite(bookId) && point) out.push({ bookId, point });
    }
  } catch {
    return [];
  }
  return out.sort((a, b) => b.point.updatedAt - a.point.updatedAt);
}

export function formatClock(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "0:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}
