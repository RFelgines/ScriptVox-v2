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

export function coverUrl(id: number): string {
  return `${API_URL}/books/${id}/cover`;
}
