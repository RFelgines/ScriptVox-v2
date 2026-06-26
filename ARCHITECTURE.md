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
├── base.py           # BaseTTSProvider — abstract async synthesise(text, voice_id, emotion=None) -> bytes
├── piper.py          # PiperProvider    — local, offline; subprocess piper.exe; voice_id → PIPER_VOICES_DIR/<id>.onnx
├── elevenlabs.py     # ElevenLabsProvider — cloud, high quality; voice_id = ElevenLabs voice UUID
├── edgetts.py        # EdgeTTSProvider  — cloud, free, no key; streams MP3 → miniaudio decode → WAV 22050 Hz
└── qwen.py           # QwenTTSProvider  — local GPU, expressive; emotion → `instruct` param; torch/qwen-tts lazy-imported
```

> **Licence Piper:** `piper-tts` est distribué sous **GPL-3.0** (`OHF-Voice/piper1-gpl`).
> Toute distribution de ScriptVox incluant Piper doit respecter cette licence.

Provider selected via env var: `TTS_PROVIDER=piper | elevenlabs | edgetts | qwen`

> **`emotion` (Phase 14 §B2)** is forwarded from `Segment.emotion` to `synthesise()`. Piper,
> ElevenLabs and EdgeTTS accept it but ignore it (no-op — none has an emotion lever).
> **`QwenTTSProvider` (§B3, 2026-06-22) is the only consumer**: `emotion` is forwarded as the
> `instruct` parameter to `generate_custom_voice`. `torch`/`qwen_tts` are heavy optional deps
> (`requirements-qwen.txt`, not in `requirements.txt`), imported lazily inside the provider —
> `app/services/tts/qwen.py` never binds them at module scope, so importing the module (or the
> factory choosing a different provider) never requires them to be installed. Model loaded once
> per provider instance (= once per Huey task), reused across `synthesise()` calls. Output is
> always 24 000 Hz from the model, resampled to 22 050 Hz via stdlib `audioop.ratecv` to match
> the other providers' WAV format. **B3 listening verdict (2026-06-27)**: speaker-preset→gender
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
   undeterminable. **Data layer only** — not yet consumed by any TTS provider (`synthesise()`
   is unchanged); it exists to feed a future Qwen3-TTS `instruct` parameter.

3. **Reconstruction (Python).** Each span becomes a
   `SegmentData(position=index, text, segment_type=DIALOGUE|NARRATION, character_name, emotion)`.
   `emotion` is only ever set on `DIALOGUE` spans (narration stays `None`) and must survive
   `_merge_chunk_results`' renumbering when a chapter is split across token-budget chunks. The
   resulting `LLMChapterResult` is otherwise **identical in shape** to the previous protocol, so
   the worker, the DB and `_merge_chunk_results` are untouched beyond propagating this field. The
   public contract `analyze(text) -> LLMChapterResult` is preserved.

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
