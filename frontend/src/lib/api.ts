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
  tts_provider: string | null;
}

export interface AppSettings {
  default_tts_provider: string;
  available_tts_providers: string[];
}

export type ProviderStatusLevel = "ok" | "warning" | "error";

export interface ProviderStatus {
  name: string;
  status: ProviderStatusLevel;
  detail: string | null;
}

export interface AppStatus {
  llm: ProviderStatus;
  tts: ProviderStatus;
  cloned_voices_count: number;
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

export type VoiceKind = "CATALOGUE" | "CLONED";

export interface VoiceSummary {
  id: string;
  name: string;
  kind: VoiceKind;
  gender: Gender | null;
  locale: string | null;
  is_favorite: boolean;
  has_reference_audio: boolean;
  has_sample: boolean;
}

export type MergeSuggestionStatus = "PENDING" | "ACCEPTED" | "REJECTED";

export interface MergeSuggestion {
  id: number;
  survivor_character_id: number;
  merged_character_id: number;
  reason: string | null;
  status: MergeSuggestionStatus;
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
  segment_count: number;
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

export async function patchBookProvider(
  bookId: number,
  ttsProvider: string | null,
): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tts_provider: ttsProvider }),
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
    throw new Error(`Changement de provider échoué : ${detail}`);
  }
  return res.json();
}

export async function getAppSettings(): Promise<AppSettings> {
  const res = await fetch(`${API_URL}/settings`);
  if (!res.ok) throw new Error(`GET /settings failed: ${res.status}`);
  return res.json();
}

export async function getAppStatus(): Promise<AppStatus> {
  const res = await fetch(`${API_URL}/settings/status`);
  if (!res.ok) throw new Error(`GET /settings/status failed: ${res.status}`);
  return res.json();
}

export async function requestVoiceSample(voiceId: string): Promise<VoiceSummary> {
  const res = await fetch(`${API_URL}/voices/${voiceId}/sample`, { method: "POST" });
  if (!res.ok) throw new Error(`POST /voices/${voiceId}/sample failed: ${res.status}`);
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

export async function createVoice(
  name: string,
  gender: Gender | null,
  file: File,
): Promise<VoiceSummary> {
  const form = new FormData();
  form.append("name", name);
  if (gender) form.append("gender", gender);
  form.append("file", file);
  const res = await fetch(`${API_URL}/voices`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // non-JSON
    }
    throw new Error(`Création de voix échouée : ${detail}`);
  }
  return res.json();
}

export async function deleteVoice(voiceId: string): Promise<void> {
  const res = await fetch(`${API_URL}/voices/${voiceId}`, { method: "DELETE" });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // non-JSON
    }
    throw new Error(`Suppression de voix échouée : ${detail}`);
  }
}

export async function patchVoiceFavorite(
  voiceId: string,
  isFavorite: boolean,
): Promise<VoiceSummary> {
  const res = await fetch(`${API_URL}/voices/${voiceId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_favorite: isFavorite }),
  });
  if (!res.ok) throw new Error(`PATCH /voices/${voiceId} failed: ${res.status}`);
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

async function _postBook(bookId: number, action: string, errorLabel: string): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/${action}`, { method: "POST" });
  if (!res.ok) {
    let detail = String(res.status);
    try { const b = await res.json(); if (b?.detail) detail = b.detail; } catch { /* ignore */ }
    throw new Error(`${errorLabel} : ${detail}`);
  }
  return res.json();
}

export function analyzeBook(bookId: number): Promise<BookSummary> {
  return _postBook(bookId, "analyze", "Analyse échouée");
}

export function generateBook(bookId: number): Promise<BookSummary> {
  return _postBook(bookId, "generate", "Génération échouée");
}

export function stopBook(bookId: number): Promise<BookSummary> {
  return _postBook(bookId, "stop", "Arrêt échoué");
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

export function voiceSampleUrl(voiceId: string): string {
  return `${API_URL}/voices/${voiceId}/sample`;
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

export async function listMergeSuggestions(bookId: number): Promise<MergeSuggestion[]> {
  const res = await fetch(`${API_URL}/books/${bookId}/merge-suggestions`);
  if (!res.ok) throw new Error(`GET /books/${bookId}/merge-suggestions failed: ${res.status}`);
  return res.json();
}

async function _resolveMergeSuggestion(
  suggestionId: number,
  action: "accept" | "reject",
): Promise<MergeSuggestion> {
  const res = await fetch(`${API_URL}/merge-suggestions/${suggestionId}/${action}`, {
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
    throw new Error(`Fusion (${action}) échouée : ${detail}`);
  }
  return res.json();
}

export function acceptMergeSuggestion(suggestionId: number): Promise<MergeSuggestion> {
  return _resolveMergeSuggestion(suggestionId, "accept");
}

export function rejectMergeSuggestion(suggestionId: number): Promise<MergeSuggestion> {
  return _resolveMergeSuggestion(suggestionId, "reject");
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
