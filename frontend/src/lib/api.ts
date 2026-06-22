const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BookStatus =
  | "PENDING"
  | "PROCESSING"
  | "ANALYZED"
  | "GENERATING"
  | "DONE"
  | "FAILED";

export interface BookSummary {
  id: number;
  title: string;
  author: string | null;
  status: BookStatus;
  progress: number;
  error_message: string | null;
  created_at: string;
  audio_path: string | null;
  mp3_path: string | null;
  cover_path: string | null;
}

export type ChapterStatus = "PENDING" | "GENERATING" | "DONE" | "FAILED";

export interface ChapterSummary {
  id: number;
  position: number;
  title: string | null;
  status: ChapterStatus;
  error_message: string | null;
}

export type Gender = "MALE" | "FEMALE" | "NEUTRAL" | "UNKNOWN";

export interface VoiceSummary {
  id: string;
  gender: Gender | null;
  locale: string | null;
}

export interface CharacterSummary {
  id: number;
  name: string;
  description: string | null;
  gender: Gender;
  age_category: string;
  tone: string | null;
  voice_quality: string | null;
  voice_tone: string | null;
  voice_id: string | null;
}

export async function listBooks(): Promise<BookSummary[]> {
  const res = await fetch(`${API_URL}/books`);
  if (!res.ok) throw new Error(`GET /books failed: ${res.status}`);
  return res.json();
}

export async function uploadBook(file: File): Promise<BookSummary> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/books`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(`Upload échoué : ${detail}`);
  }
  return res.json();
}

export async function getBook(id: number): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${id}`);
  if (!res.ok) throw new Error(`GET /books/${id} failed: ${res.status}`);
  return res.json();
}

export async function listChapters(id: number): Promise<ChapterSummary[]> {
  const res = await fetch(`${API_URL}/books/${id}/chapters`);
  if (!res.ok) throw new Error(`GET /books/${id}/chapters failed: ${res.status}`);
  return res.json();
}

export async function listCharacters(bookId: number): Promise<CharacterSummary[]> {
  const res = await fetch(`${API_URL}/books/${bookId}/characters`);
  if (!res.ok) throw new Error(`GET /books/${bookId}/characters failed: ${res.status}`);
  return res.json();
}

export async function listVoices(): Promise<VoiceSummary[]> {
  const res = await fetch(`${API_URL}/voices`);
  if (!res.ok) throw new Error(`GET /voices failed: ${res.status}`);
  return res.json();
}

export async function patchCharacterVoice(
  characterId: number,
  voiceId: string,
): Promise<CharacterSummary> {
  const res = await fetch(`${API_URL}/characters/${characterId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice_id: voiceId }),
  });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(`Override voix échoué : ${detail}`);
  }
  return res.json();
}

export async function generateBook(bookId: number): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/generate`, { method: "POST" });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(`Génération échouée : ${detail}`);
  }
  return res.json();
}

export async function deleteBook(id: number): Promise<void> {
  const res = await fetch(`${API_URL}/books/${id}`, { method: "DELETE" });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(`Suppression échouée : ${detail}`);
  }
}

export function coverUrl(id: number): string {
  return `${API_URL}/books/${id}/cover`;
}

export function bookMp3Url(id: number): string {
  return `${API_URL}/books/${id}/audio/mp3`;
}

export function chapterAudioUrl(bookId: number, position: number): string {
  return `${API_URL}/books/${bookId}/chapters/${position}/audio`;
}

export async function generateChapter(
  bookId: number,
  position: number,
): Promise<ChapterSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/${position}/generate`, {
    method: "POST",
  });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(`Génération du chapitre échouée : ${detail}`);
  }
  return res.json();
}

export async function generateAllChapters(bookId: number): Promise<ChapterSummary[]> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/generate`, {
    method: "POST",
  });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(`Génération de tous les chapitres échouée : ${detail}`);
  }
  return res.json();
}
