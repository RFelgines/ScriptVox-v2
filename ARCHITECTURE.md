# ScriptVox — Architecture Reference

## Vision

ScriptVox converts EPUB books into full multi-voice audiobooks:

1. **Ingestion** — Parse an EPUB, extract chapters and raw text.
2. **Analysis** — Use an LLM to identify the character cast and classify each dialogue
   line by speaker.
3. **Voice Assignment** — Map each character to a distinct synthetic voice.
4. **Generation** — Synthesise every line with its assigned voice and assemble the
   final audio file.

The application runs **entirely locally** (Ollama + Piper) or in **cloud mode**
(Gemini + ElevenLabs) based on environment variables — no code change required.

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

Provider selected via env var: `LLM_PROVIDER=ollama | gemini`

### 2.2 Strategy Pattern — TTS (CRITICAL)

Same principle for speech synthesis.

```
app/services/tts/
├── base.py           # BaseTTSProvider — abstract async synthesise(text, voice_id) -> bytes
├── piper.py          # PiperProvider    — local, offline; subprocess piper.exe; voice_id → PIPER_VOICES_DIR/<id>.onnx
├── elevenlabs.py     # ElevenLabsProvider — cloud, high quality; voice_id = ElevenLabs voice UUID
└── edgetts.py        # EdgeTTSProvider  — cloud, free, no key; streams MP3 → miniaudio decode → WAV 22050 Hz
```

> **Licence Piper:** `piper-tts` est distribué sous **GPL-3.0** (`OHF-Voice/piper1-gpl`).
> Toute distribution de ScriptVox incluant Piper doit respecter cette licence.

Provider selected via env var: `TTS_PROVIDER=piper | elevenlabs | edgetts`

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

| Variable                  | Default  | Purpose                                  |
|---------------------------|----------|------------------------------------------|
| `OLLAMA_CONNECT_TIMEOUT`  | 60 s     | TCP handshake + model cold-start         |
| `OLLAMA_READ_TIMEOUT`     | 600 s    | Wait for the complete LLM response       |

**Response robustness:**

- All JSON / Pydantic parsing lives inside `try/except`.
- On failure → log raw response at `ERROR` level → raise `LLMParsingError`
  (defined in `app/core/exceptions.py`).
- Never silently swallow or ignore a malformed LLM response.

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

   Everything else is narration. Undetected dialogue gracefully stays narration (spoken by
   the narrator) — **never a crash, never a dropped word** (Python owns the text).

2. **LLM call.** The numbered spans are sent, each tagged `[DIALOGUE]` / `[NARRATION]`. The
   model returns ONLY:

   ```json
   {
     "characters": [
       { "name": "...", "description": "...", "gender": "MALE|FEMALE|NEUTRAL|UNKNOWN",
         "age_category": "CHILD|YOUNG_ADULT|ADULT|ELDER|UNKNOWN",
         "tone": "...", "voice_quality": "...", "voice_tone": "..." }
     ],
     "attributions": [ { "index": 3, "character_name": "Marie" } ]
   }
   ```

   `characters[]` drives casting (schema unchanged). `attributions[]` has one entry per
   `[DIALOGUE]` span; `character_name` must match a listed character, otherwise the span
   falls back to the narrator.

3. **Reconstruction (Python).** Each span becomes a
   `SegmentData(position=index, text, segment_type=DIALOGUE|NARRATION, character_name)`.
   The resulting `LLMChapterResult` is **identical in shape** to the previous protocol, so the
   worker, the DB and `_merge_chunk_results` are untouched. The public contract
   `analyze(text) -> LLMChapterResult` is preserved.

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

## Phasing

| Phase       | Scope                                                                                        |
|-------------|----------------------------------------------------------------------------------------------|
| **Phase 1** | Foundations: FastAPI skeleton, fail-fast config, SQLModel models (`Book`, `Chapter`, `Job`), EPUB ingestion endpoint, Huey worker scaffold, job state machine |
| **Phase 2** | LLM analysis: `BaseLLMProvider`, `GeminiProvider`, `OllamaProvider`, character extraction, dialogue segmentation, token-budget chunking |
| **Phase 3** | TTS & audio: `BaseTTSProvider`, `PiperProvider`, `ElevenLabsProvider`, voice assignment, audio file assembly |
