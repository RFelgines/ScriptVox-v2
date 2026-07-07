# ScriptVox

Convert an EPUB book into a full multi-voice audiobook.  
Runs with **EdgeTTS** (free, no key, internet required — default), **locally** (Ollama + Piper), or with **Qwen3-TTS** (local GPU, emotion per line) — no code change required, only environment variables.

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

cp .env.example .env
# Edit .env — see Configuration below
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the values for your chosen providers.

| Variable | Required when | Description |
|---|---|---|
| `LLM_PROVIDER` | always | `ollama` (local) or `gemini` (cloud) |
| `OLLAMA_BASE_URL` | `LLM_PROVIDER=ollama` | Ollama server URL, e.g. `http://localhost:11434` |
| `OLLAMA_MODEL` | `LLM_PROVIDER=ollama` | Model name, e.g. `llama3` |
| `OLLAMA_CONTEXT_TOKENS` | `LLM_PROVIDER=ollama` | Context window size — **32768 recommended** (8192 truncates responses on real novel chapters) |
| `GEMINI_API_KEY` | `LLM_PROVIDER=gemini` | Gemini API key |
| `GEMINI_MODEL` | `LLM_PROVIDER=gemini` | Model name, e.g. `gemini-2.0-flash` |
| `TTS_PROVIDER` | always | `edgetts` (default, free) · `piper` (local) · `qwen` (local GPU, emotion) |
| `EDGETTS_LOCALE` | `TTS_PROVIDER=edgetts` | BCP-47 locale for voice selection, e.g. `en-US` (default), `fr-FR` |
| `PIPER_VOICES_DIR` | `TTS_PROVIDER=piper` | Path to the folder containing `.onnx` voice files |
| `PIPER_BINARY_PATH` | `TTS_PROVIDER=piper` | Path to the `piper` executable (see Piper binary below) |
| `QWEN_MODEL` | `TTS_PROVIDER=qwen` | `1.7b` (default) or `0.6b` — see Qwen3-TTS below |
| `QWEN_LANGUAGE` | `TTS_PROVIDER=qwen` | Language passed to the model, e.g. `French` (default) |
| `QWEN_DEVICE` | `TTS_PROVIDER=qwen` | torch device string, default `cuda:0` |
| `QWEN_ATTN` | `TTS_PROVIDER=qwen` | `sdpa` (default, no FlashAttention 2) or `flash_attention_2` |
| `DATABASE_URL` | always | SQLite path, e.g. `sqlite:///./scriptvox.db` |
| `HUEY_DB_PATH` | always | Huey task queue DB path, e.g. `./huey.db` |

The app **fails at startup** if any required variable for the active provider is missing, if `PIPER_VOICES_DIR` does not point to an existing directory, or if `PIPER_BINARY_PATH` does not point to an existing file. EdgeTTS requires no file on disk — only an internet connection at synthesis time.

---

## Database migrations (Alembic)

Schema changes are applied via [Alembic](https://alembic.sqlalchemy.org/), not `SQLModel.metadata.create_all()`. This matters because `create_all()` only ever creates *missing* tables — it never alters an existing one, so every model change previously required deleting `scriptvox.db` and losing the whole library.

**You don't need to run anything manually for this.** `init_db()` (called at API startup) brings the schema up to date automatically every time the app starts:

- **New database** (file doesn't exist yet) → all tables are created via the migration history, equivalent to the old `create_all()`.
- **Existing database created before Alembic was adopted** (i.e. any `scriptvox.db` from before this feature — has tables but no migration history) → auto-stamped at the current baseline revision. Stamping only records "this DB is already at revision X" in a new `alembic_version` table; it never re-runs `CREATE TABLE` or touches existing rows.
- **Database already tracked by Alembic** → any migrations newer than its current revision are applied normally.

**When you (or an agent) change a `SQLModel` model**, generate the migration by hand:

```bash
alembic revision --autogenerate -m "short description"
```

Review the generated file in `migrations/versions/` before committing — autogenerate is a good first draft, not a guarantee (it can miss things like renamed columns, which look like a drop + an add). The migration runs automatically on next startup; there is no separate `alembic upgrade` step to remember.

`migrations/env.py` reads `DATABASE_URL` from `.env`, the same source of truth as `app/config.py` — always targeting whichever database the app itself is configured for.

---

## Launch

Three processes must run in parallel:

```bash
# Terminal 1 — API server
uvicorn app.main:app --reload

# Terminal 2 — Huey background worker
.venv\Scripts\python -m huey.bin.huey_consumer app.workers.tasks.huey

# Terminal 3 — Frontend (Next.js)
cd frontend
npm run dev
```

| Process | URL |
|---|---|
| API | `http://localhost:8000` — interactive docs at `/docs` |
| Frontend | `http://localhost:3000` |

**Frontend setup (first time only):**

```bash
cd frontend
cp .env.example .env.local   # already contains NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
```

---

## EdgeTTS (default TTS)

EdgeTTS streams audio from Microsoft's neural TTS service — the same engine behind Edge browser's Read Aloud. It is **free, requires no API key and no local binary**. The only requirement is an internet connection at synthesis time.

Set `TTS_PROVIDER=edgetts` in `.env` (it is the default). Optionally set `EDGETTS_LOCALE` to control the language of the assigned voices:

| Locale | Example voices |
|---|---|
| `en-US` (default) | Christopher · Guy · Jenny · Aria · Andrew · Brian |
| `fr-FR` | Henri · Remy · Denise · Vivienne |

The voice catalogue maps logical IDs (`narrator`, `male_0` … `neutral_1`) to neural voice names automatically — no configuration needed.

> EdgeTTS output is normalised to **22050 Hz mono 16-bit WAV** by the `miniaudio` decoder before assembly, so it is fully compatible with the Piper audio format.

---

## Piper binary (local TTS)

ScriptVox invokes Piper as a **standalone executable** via subprocess — *not* the
`piper-tts` pip package. Reason: `piper-tts` depends on `piper-phonemize`, which
ships no Windows wheel. The binary approach works on every platform and keeps the
dependency out of `requirements.txt`.

1. Download the archive for your platform from
   [github.com/rhasspy/piper/releases](https://github.com/rhasspy/piper/releases)
   (e.g. `piper_windows_amd64.zip`).
2. Extract it anywhere in the project (e.g. `./piper/`). Keep the bundled
   `espeak-ng-data/` folder and the `*.dll` files **next to** `piper.exe` — Piper
   locates them relative to its own path.
3. Point `PIPER_BINARY_PATH` at the executable, e.g. `PIPER_BINARY_PATH=./piper/piper/piper.exe`.

> The licence for Piper is **GPL-3.0** (`OHF-Voice/piper1-gpl`). Any distribution of
> ScriptVox bundling the Piper binary must comply with it.

---

## Piper voices (local TTS)

`PiperProvider` loads voices from `{PIPER_VOICES_DIR}/{voice_id}.onnx`.  
The voice assignment service uses a fixed catalogue of IDs — you must supply files with **exactly these names** in your `PIPER_VOICES_DIR` folder:

| File | Role |
|---|---|
| `narrator.onnx` | Narration / stage directions |
| `male_0.onnx` | Male character pool — slot 0 |
| `male_1.onnx` | Male character pool — slot 1 |
| `male_2.onnx` | Male character pool — slot 2 |
| `female_0.onnx` | Female character pool — slot 0 |
| `female_1.onnx` | Female character pool — slot 1 |
| `female_2.onnx` | Female character pool — slot 2 |
| `neutral_0.onnx` | Neutral / unknown gender — slot 0 |
| `neutral_1.onnx` | Neutral / unknown gender — slot 1 |

> ⚠️ **Each `.onnx` file must sit next to a config named exactly `<voice_id>.onnx.json`**
> (e.g. `narrator.onnx` + `narrator.onnx.json`). Piper auto-loads `<model>.onnx.json`;
> if the config is missing or misnamed (e.g. `narrator.json`), Piper **crashes with an
> empty error** instead of reporting the problem.

**How to get voices:**

1. Browse [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) and download the `.onnx` + `.onnx.json` pair for each voice you want.
2. Rename each pair to match the IDs above (e.g. `en_US-amy-medium.onnx` → `narrator.onnx`, `en_US-amy-medium.onnx.json` → `narrator.onnx.json`).
3. Place all files in the directory pointed to by `PIPER_VOICES_DIR` (default: `./voices`).

---

## Qwen3-TTS (optional, expressive TTS — local GPU)

`QwenTTSProvider` is a 4th TTS backend that consumes the **per-line emotion** extracted by
the LLM analysis (`Segment.emotion`, e.g. *"furious and panicked"*) via Qwen3-TTS's `instruct`
parameter — the other 3 providers accept this field but ignore it.

**Status (2026-06-22): implemented, NOT yet ear-verified.** The code path is tested with mocks
only — the real model has not been validated for French audio quality or the actual effect of
`instruct` in this integration. Treat it as experimental until that listening pass happens.

**Cost of opting in:** GPU + CUDA required, ~4-6 GB VRAM, ~4.5 GB model download on first use,
and roughly **11× slower per line than EdgeTTS** (measured by `tests/spike_qwen_tts.py`).

1. Install `torch` for your CUDA version, then the rest of the optional deps:
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cu128
   pip install -r requirements-qwen.txt
   ```
2. Set `TTS_PROVIDER=qwen` in `.env` (see the `QWEN_*` variables above).

> Qwen3-TTS always returns 24 000 Hz audio; `QwenTTSProvider` resamples it to 22 050 Hz
> (stdlib `audioop`) so it stays compatible with the other providers' WAV format.

> The mapping from ScriptVox's logical voice catalogue (`narrator`, `male_0`…`neutral_1`) to
> Qwen's 9 speaker presets (`Vivian`, `Serena`, `Uncle_Fu`, `Dylan`, `Eric`, `Ryan`, `Aiden`,
> `Ono_Anna`, `Sohee`) is a best-effort guess — Qwen's own docs don't label presets by gender.
> Verify by ear once you generate real audio; see `app/services/tts/qwen.py`.

---

## Tests

Each phase has its own test suite. Run them in order to verify the full stack:

```bash
.venv\Scripts\python tests\check_phase1.py   # Config, models, DB
.venv\Scripts\python tests\check_phase2.py   # EPUB ingestion, Huey wiring
.venv\Scripts\python tests\check_phase3.py   # LLM pipeline
.venv\Scripts\python tests\check_phase4.py   # TTS, audio assembly, /audio endpoint
.venv\Scripts\python tests\check_phase5.py   # End-to-end worker pipeline (mocked LLM + TTS)
.venv\Scripts\python tests\check_phase6.py   # Per-chapter audio endpoint
.venv\Scripts\python tests\check_phase7.py   # Decoupled pipeline (ANALYZED / GENERATING statuses)
.venv\Scripts\python tests\check_phase8.py   # EdgeTTS provider (config, voice mapping, synthesis)
.venv\Scripts\python tests\check_phase9.py   # Voice casting & PATCH /characters/{id}
.venv\Scripts\python tests\check_phase10.py  # Cover image extraction & endpoints
.venv\Scripts\python tests\check_phase11.py  # MP3 output (wav_to_mp3, GET /audio/mp3)
.venv\Scripts\python tests\check_phase12.py  # CORS (Settings.frontend_origins, middleware)
.venv\Scripts\python tests\check_phase14.py  # Character persistence across chapters (known_characters)
.venv\Scripts\python tests\check_phase15.py  # QwenTTSProvider (config, voice mapping, mocked synthesis)
```

All suites mock external providers (LLM, TTS, network) and run fully offline.

---

## API quick reference

### Upload a book

```bash
curl -X POST http://localhost:8000/books \
  -F "file=@my_book.epub" \
  -F "author=Jane Doe"
```

Response (202 Accepted):

```json
{ "id": 1, "title": "my_book", "status": "PENDING", "progress": 0.0, ... }
```

### Poll status

```bash
curl http://localhost:8000/books/1
```

`status` transitions: `PENDING → PROCESSING → ANALYZED → GENERATING → DONE` (or `FAILED`).  
`progress` goes from `0.0` to `100.0`.

### Download the audiobook

```bash
curl http://localhost:8000/books/1/audio --output audiobook.wav
```

Returns 404 until `status` is `DONE`.

### Trigger audio generation (after analysis)

Once `status` reaches `ANALYZED`, trigger synthesis:

```bash
# Generate full audiobook
curl -X POST http://localhost:8000/books/1/generate

# Generate a single chapter (1-indexed position)
curl -X POST http://localhost:8000/books/1/chapters/1/generate
```

### Other endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/books` | List all books |
| `GET` | `/books/{id}/characters` | List extracted characters with their assigned `voice_id` |
| `GET` | `/books/{id}/chapters` | List chapters with per-chapter status |
| `GET` | `/books/{id}/chapters/{n}/audio` | Download a generated chapter (WAV) |
| `DELETE` | `/books/{id}` | Delete a book and its source file |

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design reference (strategy patterns, token budgeting, job state machine).

---

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal, hobby, and other noncommercial use. Commercial use requires a separate agreement with the author.
