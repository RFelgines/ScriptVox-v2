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
