# ScriptVox — Architecture Reference

## Vision

ScriptVox converts EPUB books into full multi-voice audiobooks:

1. **Ingestion** — Parse an EPUB, extract chapters and raw text.
2. **Analysis** — Use an LLM to identify the character cast and classify each dialogue
   line by speaker.
3. **Voice Assignment** — Map each character to a distinct synthetic voice.
4. **Generation** — Synthesise every line with its assigned voice and assemble the
   final audio file.

The application runs **entirely locally** (Ollama / any OpenAI-compatible server + Piper or Qwen3-TTS)
or with cloud engines (Gemini, EdgeTTS) — chosen in *Settings* or by environment variables, no code
change required. Engines the project does not know are added as **plugins** (§2.8).

---

## Stack

| Component       | Technology                                    | Notes                                             |
|-----------------|-----------------------------------------------|---------------------------------------------------|
| API Framework   | FastAPI ~0.136                                | Async, OpenAPI auto-docs                          |
| Database        | SQLite via SQLModel ~0.0.38                   | SQLModel ≥ 0.0.14 required for Pydantic V2 compat |
| ORM core        | SQLAlchemy ~2.0                               | Used by SQLModel under the hood                   |
| Task queue      | Huey ~2.5 (SQLite backend: `huey.db`)         | Separate DB from app DB                           |
| Validation      | Pydantic V2 ~2.11                             | Native SQLModel/FastAPI integration               |
| HTTP client     | httpx ~0.28 (async)                           | Granular timeouts, excellent testability          |
| LLM local SDK   | ollama-python ~0.4                            | Official async Ollama client                      |
| LLM cloud SDK   | google-genai ~2.8                             | New official SDK — replaces deprecated `google-generativeai` |
| Config          | python-dotenv ~1.0                            | Loads `.env` at startup                           |
| ASGI server     | uvicorn ~0.34                                 | Standard ASGI server for FastAPI                  |
| Audio           | miniaudio, lameenc, numpy, ffmpeg (external)  | Decode/resample, MP3, vector ops; ffmpeg = chaptered M4B (optional) |

> **Compatibility note:** SQLModel 0.0.14 introduced Pydantic V2 support. The pinned
> version (0.0.38) is fully compatible with Pydantic V2 and SQLAlchemy 2.0.

---

## Architecture Principles

### 2.1 Strategy Pattern — LLM (CRITICAL)

The system is **provider-agnostic**. A single abstract base class defines the contract;
concrete adapters handle provider specifics.

```
app/services/llm/
├── base.py        # BaseLLMProvider — abstract async analyze(text: str) -> LLMChapterResult
├── gemini.py      # GeminiProvider  — wraps google-genai SDK
└── ollama.py      # OllamaProvider  — wraps ollama-python SDK
```

Providers: `ollama`, `gemini`, `openai_compatible` (any OpenAI-API server) or a plugin. Selected by
`LLM_PROVIDER` (`.env`) or *Settings*; the **model** and server address are runtime settings
(`AppSetting.llm_options`) that take priority over `.env`. All providers are resolved through the
registry (§2.8): `llm/factory.py` no longer knows provider names.

### 2.2 Strategy Pattern — TTS (CRITICAL)

Same principle for speech synthesis.

```
app/services/tts/
├── base.py           # BaseTTSProvider — abstract async synthesise(text, voice_id, emotion=None) -> bytes
├── piper.py          # PiperProvider    — local, offline; subprocess piper.exe; voice_id → PIPER_VOICES_DIR/<id>.onnx
├── edgetts.py        # EdgeTTSProvider  — cloud, free, no key; streams MP3 → miniaudio decode → WAV 24 kHz
├── qwen.py           # QwenTTSProvider  — local GPU, expressive; emotion → `instruct`; any checkpoint id; torch lazy-imported
├── http_tts.py       # OpenAICompatibleTTSProvider — POST {base}/audio/speech, voice table, extra body
└── command.py        # CommandTTSProvider — external program, no shell, .env-only
```

> **Licence Piper:** `piper-tts` est distribué sous **GPL-3.0** (`OHF-Voice/piper1-gpl`).
> Toute distribution de ScriptVox incluant Piper doit respecter cette licence.

> **ElevenLabs retiré (2026-07-02, audit finding M2).** Un `ElevenLabsProvider` a existé mais n'a
> **jamais fonctionné** : les voice_id logiques du catalogue (`male_0`…) étaient injectés tels
> quels dans l'URL de l'API ElevenLabs, qui attend un UUID de voix réel (aucun mapping n'a jamais
> existé), et le modèle codé en dur (`eleven_monolingual_v1`) était anglais-only. Aucun test ne
> l'exerçait en conditions réelles. Supprimé plutôt que corrigé (KISS — pas de besoin identifié) ;
> voir mémoire `audit-2026-07-02-remediation-plan`, Lot D, si un besoin réel émerge un jour.

Providers: `piper`, `edgetts`, `qwen`, `openai_tts` (any `/v1/audio/speech` server), `command`
(external program) or a plugin. Selected by `TTS_PROVIDER` or *Settings* (global preference, per-book
override); runtime settings in `AppSetting.tts_options`.

`BaseTTSProvider` (`tts/base.py`) only requires `synthesise(text, voice_id, emotion, reference_audio_path)
-> bytes`. Optional class attributes: `supports_concurrency` (parallel calls), `max_chars` (longer texts
are split at sentence ends), `keep_loaded` (worker keeps the loaded model between chapters) and
`unload()`. **Any decodable audio format is accepted** — `app/services/audio/format.normalize_audio`
converts to the pipeline format (WAV mono 16-bit 24 kHz) in `_synthesise_with_retry`.

> **`emotion` (Phase 14 §B2)** is forwarded from `Segment.emotion` to `synthesise()`. Piper
> and EdgeTTS accept it but ignore it (no-op — neither has an emotion lever).
> **`QwenTTSProvider` (§B3, 2026-06-22) is the only consumer**: `emotion` is forwarded as the
> `instruct` parameter to `generate_custom_voice`. `torch`/`qwen_tts` are heavy optional deps
> (`requirements-qwen.txt`, not in `requirements.txt`), imported lazily inside the provider —
> `app/services/tts/qwen.py` never binds them at module scope, so importing the module (or the
> factory choosing a different provider) never requires them to be installed. Model loaded once
> per provider instance (= once per Huey task), reused across `synthesise()` calls. Output is
> always 24 000 Hz from the model, passed through unchanged (the pipeline format is 24 kHz; the previous 22 050 Hz resampling via the
> removed `audioop` module is gone). **B3 listening verdict (2026-06-27)**: speaker-preset→gender
> mapping in `_VOICE_MAP` confirmed correct (no remap needed); French quality is variable (some
> presets carry a perceptible "British" accent — accepted as a Qwen preset limitation, not an
> integration bug); the `instruct` emotion parameter is inconclusive (not consistently better than
> without) but does not block voice cloning, which uses `generate_custom_voice` with a reference
> sample rather than `instruct`.

> `edgetts` is the default (`TTS_PROVIDER=edgetts` in `.env.example`). It requires internet
> access at synthesis time and no API key. Optional: `EDGETTS_LOCALE` (default `en-US`).

### 2.3 Token Budgeting (IMPORTANT)

- **No static truncation** anywhere in the codebase.
- Controlled by `OLLAMA_CONTEXT_TOKENS` (set in `.env`).
- **Chunking unit:** EPUB chapter (natural boundary).
- **Overflow strategy:** recursive split by paragraph if a chapter exceeds the budget.
- **Safety margin:** 20 % of the context window is reserved for the system prompt and the
  model's response. Effective content budget = `floor(OLLAMA_CONTEXT_TOKENS × 0.8)`.
  This `× 0.8` is only valid because the analysis protocol is **label-based** (§2.7): the
  model never echoes the input text, so its response stays small — O(dialogue spans), not
  O(input tokens). The earlier "reproduce every word" prompt violated this: its response was
  as large as its input, leaving an effective input budget closer to `context_window / 3`.

### 2.4 KISS & Fail-Fast (IMPORTANT)

- Simplest solution that fulfils the requirement; no speculative abstractions.
- On startup (`app/config.py`), validate **all** required env vars. If any is absent:
  ```python
  raise ValueError("Missing required env var: <NAME>")
  ```
- Never start in a silently degraded state.

### 2.5 LLM Call Resilience (IMPORTANT)

**Ollama timeouts (via httpx `Timeout` object):**

| Variable                        | Default  | Purpose                                          |
|----------------------------------|----------|---------------------------------------------------|
| `OLLAMA_CONNECT_TIMEOUT`        | 60 s     | TCP handshake + model cold-start                  |
| `OLLAMA_READ_TIMEOUT`           | 600 s    | Floor for the per-request read timeout            |
| `OLLAMA_TIMEOUT_PER_1K_TOKENS`  | 200 s    | Extra read-timeout budget per 1000 estimated prompt tokens |

**Dynamic read timeout (2026-06-22/23, found on a real HP run — a dense chapter exceeded a
fixed `OLLAMA_READ_TIMEOUT` twice, once at 600 s and again at 1200 s).** A single fixed timeout
either cuts off a legitimately slow request (dense chapter, and/or a local model partially
offloaded to CPU when VRAM is tight — `ollama ps` showing e.g. `31% CPU` is a sign of this,
*not* a code bug) or wastes time waiting on small chapters. `OllamaProvider` computes the read
timeout per request as `floor + (estimated_prompt_tokens / 1000) * per_1k_tokens`
(`_compute_read_timeout` in `app/services/llm/base.py`, reuses `_estimate_tokens`), mutating the
underlying `httpx.AsyncClient.timeout` (`self._client._client`, read fresh by httpx on every
request — verified) right before each `chat()` call in both `analyze` and `suggest_merges`. This
does **not** fix CPU-fallback slowness itself (still governed by the `num_ctx` trade-off,
§2.3) — it only ensures the timeout scales with the work requested instead of an arbitrary fixed
ceiling. `GeminiProvider` is unaffected (cloud API, no local VRAM contention, no configurable
timeout existed before this).

**Constrained output (audit 2026-09-25).** The engines are given the JSON Schema of the expected answer
(`ANALYSIS_JSON_SCHEMA` / `MERGE_JSON_SCHEMA` in `llm/base.py`): Ollama `format=`, Gemini
`response_json_schema`, OpenAI `response_format=json_schema` (with automatic fallback to `json_object`
then text). `_parse_llm_json` stays the safety net. Sampling temperature: `LLM_TEMPERATURE` (0.2).
Gemini retries 429/503 with 5 s / 15 s / 45 s back-off.

**Response robustness:**

- All JSON / Pydantic parsing lives inside `try/except`.
- On failure → log raw response at `ERROR` level → raise `LLMParsingError`
  (defined in `app/core/exceptions.py`).
- Never silently swallow or ignore a malformed LLM response.

**Two distinct failure modes, two distinct exceptions (2026-06-22, found on a real HP run —
a chapter exceeded `OLLAMA_READ_TIMEOUT`).** `OllamaProvider`/`GeminiProvider` (`analyze` and
`suggest_merges`) wrap *only* the network call in `try/except Exception -> raise LLMRequestError(exc)`
(no response received, nothing to log). `_parse_llm_json`/`_parse_merge_json` (`app/services/llm/base.py`)
independently raise `LLMParsingError` on a malformed/unparseable response. The two used to be
conflated (a single broad `except Exception` around both the network call *and* the parsing,
always raising `LLMParsingError` even on a timeout) — a `ReadTimeout` then surfaced as
`"LLM response parsing failed: "` with an empty raw response, hiding the real cause. Both are
plain `Exception` subclasses, so the worker's generic `except Exception as exc: error_message =
str(exc)` (`app/workers/tasks.py`) needs no change — only `str(exc)` becomes accurate.

### 2.6 Job State Machine (CRITICAL)

Every long-running task is tracked in the database from creation.

```
PENDING → PROCESSING → ANALYZED → GENERATING → DONE
               ↘ FAILED              ↘ FAILED
```

| Status | Meaning |
|--------|---------|
| `PENDING` | Book created, worker not started yet |
| `PROCESSING` | EPUB parse + LLM analysis in progress |
| `ANALYZED` | Analysis complete; characters, segments and voice assignments populated; ready for audio generation |
| `GENERATING` | TTS synthesis + audio assembly in progress |
| `DONE` | Audio file ready; `audio_path` populated |
| `FAILED` | Terminal error; `error_message` populated verbatim |

- `error_message` stores the failure reason verbatim.
- Mandatory from Phase 1 — this is the foundation of observability.
- Worker entry points: `analyze_book` (Huey task → `_analyze_book_impl`) and
  `generate_book` (Huey task → `_generate_book_impl`).
  `process_book` (legacy) chains both and is preserved for backward compatibility.

### 2.7 LLM Analysis Protocol — Label-Based (CRITICAL)

The LLM **never reproduces the chapter text**. It only labels structure. This keeps local
inference fast (response size = O(dialogue spans), not O(input tokens)) and is what makes the
§2.3 token budget (`× 0.8`) correct.

**Pipeline (inside `app/services/llm/base.py`):**

1. **Pre-segmentation (deterministic, Python).** The chapter is split into ordered spans
   `(index, text, is_dialogue)` *before* the LLM call. Dialogue is detected from delimiters:
   - French guillemets `« … »` (non-breaking spaces tolerated),
   - typographic `" … "` and straight `"…"` quotes,
   - lines opened by an em-dash `—` / `–` (French dialogue turns).

   **Incise extraction.** Em-dash dialogue lines often embed an attribution clause with no
   delimiter of its own (`— Je ne te crois pas, dit-elle froidement.`). `_split_incise` peels
   that incise off into its own **narration** span (read by the narrator, not the character),
   detected via verb-subject inversion (`dit-elle`, `demanda-t-elle`, `dit Harry`). It is only
   extracted when terminal and clean (no comma after the verb): a *resumed* dialogue
   (`…, répondit-il, mais je viendrai`) stays one dialogue span — bounded degradation. Guillemets
   dialogue is untouched (its incise already falls outside `« … »`).

   Everything else is narration. Undetected dialogue gracefully stays narration (spoken by
   the narrator) — **never a crash, never a dropped word** (Python owns the text). Invariant:
   `"".join(s.text for s in spans) == text` with contiguous 1-based indices.

2. **LLM call.** The numbered spans are sent, each tagged `[DIALOGUE]` / `[NARRATION]`. The
   model returns ONLY:

   ```json
   {
     "characters": [
       { "name": "...", "description": "...", "gender": "MALE|FEMALE|NEUTRAL|UNKNOWN",
         "age_category": "CHILD|YOUNG_ADULT|ADULT|ELDER|UNKNOWN",
         "tone": "...", "voice_quality": "...", "voice_tone": "..." }
     ],
     "attributions": [ { "index": 3, "character_name": "Marie", "emotion": "furious and panicked" } ]
   }
   ```

   `characters[]` drives casting (schema unchanged). `attributions[]` has one entry per
   `[DIALOGUE]` span; `character_name` must match a listed character, otherwise the span
   falls back to the narrator. `emotion` (Phase 14 §B1) is free text describing how the line
   should be delivered (e.g. `"soft and hesitant"`, `"calm"`); optional, `null`/absent if
   undeterminable. Forwarded to `synthesise()` (§2.2): Qwen3-TTS uses it as `instruct`; other engines
   ignore it or map it.

3. **Reconstruction (Python).** Each span becomes a
   `SegmentData(position=index, text, segment_type=DIALOGUE|NARRATION, character_name, emotion)`.
   `emotion` is only ever set on `DIALOGUE` spans (narration stays `None`) and must survive
   `_merge_chunk_results`' renumbering when a chapter is split across token-budget chunks. The
   resulting `LLMChapterResult` is otherwise **identical in shape** to the previous protocol, so
   the worker, the DB and `_merge_chunk_results` are untouched beyond propagating this field. The
   public contract `analyze(text) -> LLMChapterResult` is preserved.

### 2.6b Chapter states and generation through the queue (audit 2026-09-25)

```
Chapter:  PENDING ─(queued_at set)─▶ GENERATING ─▶ DONE
              ▲                          │  └────▶ FAILED
              └── abort / re-queue ◀─────┘        (re-queue: DONE/FAILED → PENDING)
```

`POST /books/{id}/generate` no longer runs one multi-hour task: it queues every included, unfinished
chapter (`Chapter.queued_at`) and the **pump** (`generate_chapter_queue_pump`) processes **one chapter
per Huey task**, re-enqueuing itself while the queue is not empty. Short tasks (`generate_segment`,
`generate_voice_sample`, `generate_character_preview`, `release_qwen_vram`) have a higher Huey priority
and run between two chapters. After every chapter `_advance_books` updates the progress and, when all
included chapters are DONE, assembles WAV + MP3 + M4B and flips the book to DONE; a FAILED chapter fails
the book (resume keeps the DONE chapters). `_generate_book_impl` (synchronous, whole book in one call)
remains for `process_book` and tests. `Chapter.included=False` (cover, copyright, TOC — detected at
import, editable in the UI) skips a chapter everywhere.

Progress: `Book.progress` (legacy global 0-100) plus `stage` (`analysis|generation|assembly`),
`stage_progress` and `eta_seconds` (moving average of the measured throughput).

### 2.8 Engine registry and plugins

`app/services/registry.py` maps provider names to factories `(settings, options[, language]) → provider`.
Official engines are registered there (lazy imports); plugins are Python files in
`plugins/llm/` and `plugins/tts/` (`PROVIDER_NAME`, `create(settings, options)`, optional `DESCRIPTION`
and `list_models`), loaded once, **isolated** (a broken plugin is skipped and reported in Settings).
`Settings` validates `LLM_PROVIDER` / `TTS_PROVIDER` against the registry. Runtime overrides live in
`AppSetting.llm_options` / `tts_options` (whitelisted keys `model`, `base_url`, `base_model`, `locale`;
secrets and `TTS_COMMAND` are `.env`-only). See `docs/PLUGINS.md`.

The worker keeps providers that declare `keep_loaded=True` in a process-level cache (`_TTS_CACHE`):
the Qwen model is loaded once per book, unloaded after `TTS_IDLE_UNLOAD_SECONDS`, on request, or before
an analysis. The local LLM is unloaded at the end of an analysis (`LLM_UNLOAD_AFTER_ANALYSIS`).

### 2.9 Audio pipeline

`app/services/audio/`:

- `format.py` — the single pipeline format (**WAV mono 16-bit 24 kHz**); `normalize_audio` converts any
  provider output; helpers for silence, loudness (`adjust_level`, bounded ±6 dB) and sentence splitting.
- `chapter.py` — synthesises a chapter: sentence splitting above the provider's `max_chars`, optional
  concurrency (`supports_concurrency`), loudness normalisation, **pauses** (same voice / voice change),
  `audio_offset_ms` including the pauses (the transcript highlighting depends on it).
- `assembler.py` — streaming disk-to-disk assembly; `target_rate` converts chapters generated at another
  rate on the fly; `gaps_ms` inserts silence between chapters.
- `m4b.py` — chaptered M4B with cover through ffmpeg (optional).

### 2.10 Security model

Local single-user application, no authentication. The API refuses cross-site writes (`Origin` must be in
`FRONTEND_ORIGINS`, or absent for non-browser clients) and unknown `Host` headers (`ALLOWED_HOSTS`);
CORS is restricted to the frontend origins; EPUBs are checked against decompression bombs; SQLite runs in
WAL mode with a busy timeout. See `SECURITY.md`.

### 2.11 Storage layout (`DATA_DIR`)

```
DATA_DIR/
├── <uuid>.epub|.wav|.mp3|.m4b     # source upload and the assembled book (next to each other)
├── <book_id>/
│   ├── cover.<ext>
│   ├── ch<N>.wav                  # generated chapters (24 kHz)
│   ├── takes/<take_id>.wav        # per-line takes (regeneration, take selection)
│   └── previews/<char>_<voice>_<hash>.wav
├── voices/<slug>/ref.<ext>|ref.txt   # cloned-voice reference audio and transcript
└── voice_samples/                 # cached voice previews
```

---

## Work Protocol

1. **Plan-First** — Propose a detailed step-by-step plan and wait for explicit `GO`
   before writing any file.
2. **Blast Radius** — Touch only the file / feature in scope. Never modify other files
   without explicit authorisation.
3. **Auto-Verify** — At each logical checkpoint, provide a `curl` command or a Python
   test script to validate before continuing.
4. **No Surprise Dependencies** — Never add an unlisted library without proposing it
   first with justification.

---

## Status

The original three phases (Foundations, LLM analysis, TTS & audio) are complete; the roadmap since then
(casting, cloning, generation queue, UI, engine registry, audit 2026-09-25) is tracked in `TASKS.md`
and `CHANGELOG.md`, with the detailed journal in `docs/journal/`.
