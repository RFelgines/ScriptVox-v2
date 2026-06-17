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
  status: BookStatus;
  progress: number;
  created_at: string;
  audio_path: string | null;
  mp3_path: string | null;
  cover_path: string | null;
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

export function coverUrl(id: number): string {
  return `${API_URL}/books/${id}/cover`;
}
