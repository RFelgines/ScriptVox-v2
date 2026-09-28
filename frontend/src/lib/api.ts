import { getStoredLocale, translations, type Dictionary } from "@/lib/i18n/translations";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function t() {
  return translations[getStoredLocale()];
}

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
  failed_stage: "analysis" | "generation" | null;
  created_at: string;
  audio_path: string | null;
  mp3_path: string | null;
  m4b_path: string | null;
  cover_path: string | null;
  tts_provider: string | null;
  genre: string | null;
  language: string | null;
  published_at: string | null;
  // Étape en cours, avancement dans l'étape (0-100) et temps restant estimé.
  stage: "analysis" | "generation" | "assembly" | null;
  stage_progress: number;
  eta_seconds: number | null;
}

// Réglages à chaud d'un moteur (priment sur le .env). Toute valeur est libre : un modèle
// absent des listes proposées est accepté tel quel.
export interface EngineOptions {
  model?: string;
  base_url?: string;
  base_model?: string;
  locale?: string;
}

export interface PluginError {
  file: string;
  error: string;
}

export interface AppSettings {
  default_tts_provider: string;
  preferred_tts_provider: string | null;
  available_tts_providers: string[];
  default_llm_provider: string;
  preferred_llm_provider: string | null;
  available_llm_providers: string[];
  /** Codes de langue que l'application sait traiter de bout en bout (un
   *  LanguageProfile existe côté serveur). Sert à signaler les livres dont la
   *  langue n'est pas prise en charge -- voir BookCard. */
  available_languages: string[];
  preferred_language: string | null;
  llm_options: EngineOptions;
  tts_options: EngineOptions;
  effective_llm_model: string | null;
  effective_tts_model: string | null;
  llm_provider_descriptions: Record<string, string>;
  tts_provider_descriptions: Record<string, string>;
  plugin_errors: PluginError[];
}

export interface SettingsPatch {
  preferred_tts_provider?: string | null;
  preferred_llm_provider?: string | null;
  llm_options?: EngineOptions;
  tts_options?: EngineOptions;
}

export interface ModelList {
  provider: string;
  models: string[];
  error: string | null;
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
  priority: number;
  included: boolean;
  duration_ms: number | null;
}

export interface QueueItem {
  chapter_id: number;
  book_id: number;
  book_title: string;
  position: number;
  title: string | null;
  status: ChapterStatus;
  priority: number;
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
  has_reference_text: boolean;
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
    throw new Error(t().errors.upload(detail));
  }
  return res.json();
}

export async function getBook(id: number): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${id}`);
  if (!res.ok) throw new Error(`GET /books/${id} failed: ${res.status}`);
  return res.json();
}

async function _patchBookField(
  bookId: number,
  field: string,
  value: string | null,
  fieldKey: keyof Dictionary["errors"]["fields"],
): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [field]: value }),
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
    const dict = t();
    throw new Error(dict.errors.fieldChange(dict.errors.fields[fieldKey], detail));
  }
  return res.json();
}

export function patchBookProvider(bookId: number, ttsProvider: string | null): Promise<BookSummary> {
  return _patchBookField(bookId, "tts_provider", ttsProvider, "ttsProvider");
}

export function patchBookGenre(bookId: number, genre: string | null): Promise<BookSummary> {
  return _patchBookField(bookId, "genre", genre, "genre");
}

export function patchBookLanguage(bookId: number, language: string | null): Promise<BookSummary> {
  return _patchBookField(bookId, "language", language, "language");
}

export function patchBookPublishedAt(
  bookId: number,
  publishedAt: string | null,
): Promise<BookSummary> {
  return _patchBookField(bookId, "published_at", publishedAt, "publishedAt");
}

export async function getAppSettings(): Promise<AppSettings> {
  const res = await fetch(`${API_URL}/settings`);
  if (!res.ok) throw new Error(`GET /settings failed: ${res.status}`);
  return res.json();
}

// Message d'erreur lisible d'une réponse d'API (champ `detail` de FastAPI, texte ou liste).
export async function detailOf(res: Response): Promise<string> {
  let detail = String(res.status);
  try {
    const body = await res.json();
    if (body?.detail) {
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    // réponse non-JSON : on garde le code HTTP
  }
  return detail;
}

export async function updateAppSettings(patch: SettingsPatch): Promise<AppSettings> {
  const res = await fetch(`${API_URL}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`PATCH /settings : ${await detailOf(res)}`);
  return res.json();
}

// deep=true : appels réels aux services distants (bouton « Tester la connexion »).
export async function getAppStatus(deep = false): Promise<AppStatus> {
  const res = await fetch(`${API_URL}/settings/status${deep ? "?deep=true" : ""}`);
  if (!res.ok) throw new Error(`GET /settings/status failed: ${res.status}`);
  return res.json();
}

// Décharge les modèles TTS gardés en mémoire (VRAM) — tâche courte côté worker.
export async function unloadModels(): Promise<void> {
  const res = await fetch(`${API_URL}/models/qwen/unload`, { method: "POST" });
  if (!res.ok) throw new Error(`POST /models/qwen/unload : ${await detailOf(res)}`);
}

// Suggestions de modèles (installés localement quand le moteur sait les lister). Ne lève
// jamais côté serveur : une erreur réseau arrive dans `error`.
export async function listModels(kind: "llm" | "tts", provider?: string): Promise<ModelList> {
  const params = new URLSearchParams({ kind });
  if (provider) params.set("provider", provider);
  const res = await fetch(`${API_URL}/settings/models?${params.toString()}`);
  if (!res.ok) throw new Error(`GET /settings/models : ${await detailOf(res)}`);
  return res.json();
}

export async function requestVoiceSample(voiceId: string): Promise<VoiceSummary> {
  const res = await fetch(`${API_URL}/voices/${voiceId}/sample`, { method: "POST" });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(t().errors.voiceSample(detail));
  }
  return res.json();
}

export interface SegmentSummary {
  id: number;
  position: number;
  text: string;
  segment_type: string;
  character_name: string | null;
  voice_id: string | null;
  audio_offset_ms: number | null;
  duration_ms: number | null;
}

export async function getChapterSegments(
  bookId: number,
  position: number,
): Promise<SegmentSummary[]> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/${position}/segments`);
  if (!res.ok) throw new Error(`GET segments failed: ${res.status}`);
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
  referenceText?: string,
): Promise<VoiceSummary> {
  const form = new FormData();
  form.append("name", name);
  if (gender) form.append("gender", gender);
  if (referenceText && referenceText.trim()) form.append("reference_text", referenceText.trim());
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
    throw new Error(t().errors.voiceCreate(detail));
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
    throw new Error(t().errors.voiceDelete(detail));
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
    throw new Error(t().errors.voiceOverride(detail));
  }
  return res.json();
}

async function _postBook(
  bookId: number,
  action: string,
  actionKey: keyof Dictionary["errors"]["actions"],
): Promise<BookSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/${action}`, { method: "POST" });
  if (!res.ok) {
    let detail = String(res.status);
    try { const b = await res.json(); if (b?.detail) detail = b.detail; } catch { /* ignore */ }
    const dict = t();
    throw new Error(dict.errors.bookAction(dict.errors.actions[actionKey], detail));
  }
  return res.json();
}

export function analyzeBook(bookId: number, force = false): Promise<BookSummary> {
  return _postBook(bookId, force ? "analyze?force=true" : "analyze", "analyze");
}

export function generateBook(bookId: number, force = false): Promise<BookSummary> {
  return _postBook(bookId, force ? "generate?force=true" : "generate", "generate");
}

export function stopBook(bookId: number): Promise<BookSummary> {
  return _postBook(bookId, "stop", "stop");
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
    throw new Error(t().errors.bookDelete(detail));
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

export function bookM4bUrl(id: number): string {
  return `${API_URL}/books/${id}/audio/m4b`;
}

export function characterPreviewUrl(characterId: number, voiceId: string): string {
  return `${API_URL}/characters/${characterId}/preview?voice_id=${encodeURIComponent(voiceId)}`;
}

// Inclure / exclure un chapitre (page non narrative : couverture, copyright, sommaire…).
export async function patchChapterIncluded(
  bookId: number,
  position: number,
  included: boolean,
): Promise<ChapterSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/${position}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ included }),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

// Lance la génération (tâche courte et prioritaire côté worker) d'un aperçu de la voix sur une
// réplique du personnage ; `ready: true` = déjà en cache.
export async function requestCharacterPreview(
  characterId: number,
  voiceId: string,
): Promise<{ ready: boolean }> {
  const res = await fetch(`${API_URL}/characters/${characterId}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice_id: voiceId }),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

export async function characterPreviewReady(characterId: number, voiceId: string): Promise<boolean> {
  // GET (l'API ne répond pas à HEAD) : l'aperçu est un petit WAV de quelques secondes.
  const res = await fetch(characterPreviewUrl(characterId, voiceId));
  return res.ok;
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
    throw new Error(t().errors.chapterGenerate(detail));
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
    throw new Error(t().errors.mergeResolve(action, detail));
  }
  return res.json();
}

export function acceptMergeSuggestion(suggestionId: number): Promise<MergeSuggestion> {
  return _resolveMergeSuggestion(suggestionId, "accept");
}

export function rejectMergeSuggestion(suggestionId: number): Promise<MergeSuggestion> {
  return _resolveMergeSuggestion(suggestionId, "reject");
}

export async function getQueue(): Promise<QueueItem[]> {
  const res = await fetch(`${API_URL}/chapters/queue`);
  if (!res.ok) throw new Error(`GET /chapters/queue failed: ${res.status}`);
  return res.json();
}

export async function stopChapter(bookId: number, position: number): Promise<ChapterSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/${position}/stop`, {
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
    throw new Error(t().errors.chapterStop(detail));
  }
  return res.json();
}

export async function patchChapterPriority(
  bookId: number,
  position: number,
  priority: number,
): Promise<ChapterSummary> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/${position}/priority`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ priority }),
  });
  if (!res.ok) {
    let detail = String(res.status);
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // réponse non-JSON : on garde le code HTTP
    }
    throw new Error(t().errors.chapterPriority(detail));
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
    throw new Error(t().errors.allChaptersGenerate(detail));
  }
  return res.json();
}

export interface SegmentTake {
  id: number;
  segment_id: number;
  audio_path: string | null;
  voice_id: string;
  emotion: string | null;
  is_selected: boolean;
  created_at: string;
}

export async function regenerateSegment(
  bookId: number,
  chapterPosition: number,
  segmentId: number,
  opts: { voice_id: string; emotion?: string },
): Promise<SegmentTake> {
  const res = await fetch(
    `${API_URL}/books/${bookId}/chapters/${chapterPosition}/segments/${segmentId}/regenerate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    },
  );
  if (!res.ok) throw new Error(`POST regenerate failed: ${res.status}`);
  return res.json();
}

export async function selectTake(
  bookId: number,
  chapterPosition: number,
  segmentId: number,
  takeId: number,
): Promise<SegmentTake> {
  const res = await fetch(
    `${API_URL}/books/${bookId}/chapters/${chapterPosition}/segments/${segmentId}/takes/${takeId}/select`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`POST select failed: ${res.status}`);
  return res.json();
}

// ── Production de livres audio ─────────────────────────────────────────────────

// Horodatage des chapitres (« HH:MM:SS Titre » par ligne), écrit à l'assemblage du livre.
export function bookChaptersTxtUrl(id: number): string {
  return `${API_URL}/books/${id}/audio/chapters.txt`;
}

// Extrait (~1 min) du début d'un chapitre, rendu comme le chapitre final.
export function chapterExcerptUrl(bookId: number, position: number): string {
  return `${API_URL}/books/${bookId}/chapters/${position}/excerpt`;
}

export async function requestChapterExcerpt(bookId: number, position: number): Promise<{ ready: boolean }> {
  const res = await fetch(chapterExcerptUrl(bookId, position), { method: "POST" });
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

export async function chapterExcerptReady(bookId: number, position: number): Promise<boolean> {
  const res = await fetch(chapterExcerptUrl(bookId, position));
  return res.ok;
}

export interface LoudnessReport {
  rms_dbfs: number | null;
  peak_dbfs: number | null;
  noise_floor_dbfs: number | null;
  digital_silence: boolean;
  duration_s: number;
  checks: { rms: boolean; peak: boolean; noise_floor: boolean };
  acx_compliant: boolean;
}

export async function getChapterLoudness(bookId: number, position: number): Promise<LoudnessReport> {
  const res = await fetch(`${API_URL}/books/${bookId}/chapters/${position}/loudness`);
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

// Lexique de prononciation (book_id null = entrée globale).
export interface LexiconEntry {
  id: number;
  book_id: number | null;
  term: string;
  replacement: string;
  whole_word: boolean;
  case_sensitive: boolean;
}

export async function listLexicon(bookId?: number): Promise<LexiconEntry[]> {
  const q = bookId !== undefined ? `?book_id=${bookId}` : "";
  const res = await fetch(`${API_URL}/lexicon${q}`);
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

export async function createLexiconEntry(
  entry: Omit<LexiconEntry, "id">,
): Promise<LexiconEntry> {
  const res = await fetch(`${API_URL}/lexicon`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

export async function deleteLexiconEntry(id: number): Promise<void> {
  const res = await fetch(`${API_URL}/lexicon/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new Error(await detailOf(res));
}

export async function previewLexicon(text: string, bookId?: number): Promise<string> {
  const res = await fetch(`${API_URL}/lexicon/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, book_id: bookId ?? null }),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  return (await res.json()).text;
}

// Voix conçue d'un personnage (OmniVoice) : description proposée, puis conception.
export interface VoiceDesignInfo {
  suggested_instruct: string;
  designed_voice_id: string | null;
  current_instruct: string | null;
  assigned: boolean;
}

export async function getVoiceDesign(characterId: number): Promise<VoiceDesignInfo> {
  const res = await fetch(`${API_URL}/characters/${characterId}/voice-design`);
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}

export async function requestVoiceDesign(
  characterId: number,
  instruct: string,
): Promise<{ voice_id: string; instruct: string }> {
  const res = await fetch(`${API_URL}/characters/${characterId}/voice-design`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruct }),
  });
  if (!res.ok) throw new Error(await detailOf(res));
  return res.json();
}
