# ScriptVox

Convert an EPUB book into a full multi-voice audiobook.  
Runs **entirely locally** (Ollama + Piper) or in **cloud mode** (Gemini + ElevenLabs) — no code change required, only environment variables.

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
| `OLLAMA_CONTEXT_TOKENS` | `LLM_PROVIDER=ollama` | Context window size (default 8192) |
| `GEMINI_API_KEY` | `LLM_PROVIDER=gemini` | Gemini API key |
| `GEMINI_MODEL` | `LLM_PROVIDER=gemini` | Model name, e.g. `gemini-2.0-flash` |
| `TTS_PROVIDER` | always | `piper` (local) or `elevenlabs` (cloud) |
| `PIPER_VOICES_DIR` | `TTS_PROVIDER=piper` | Path to the folder containing `.onnx` voice files |
| `ELEVENLABS_API_KEY` | `TTS_PROVIDER=elevenlabs` | ElevenLabs API key |
| `DATABASE_URL` | always | SQLite path, e.g. `sqlite:///./scriptvox.db` |
| `HUEY_DB_PATH` | always | Huey task queue DB path, e.g. `./huey.db` |

The app **fails at startup** if any required variable for the active provider is missing or if `PIPER_VOICES_DIR` does not point to an existing directory.

---

## Launch

Two processes must run in parallel:

```bash
# Terminal 1 — API server
uvicorn app.main:app --reload

# Terminal 2 — Huey background worker
.venv\Scripts\python -m huey.bin.huey_consumer app.workers.tasks.huey
```

The API is available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

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

Each `.onnx` file must be accompanied by its `.onnx.json` config file (Piper requirement).

**How to get voices:**

1. Browse [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) and download the `.onnx` + `.onnx.json` pair for each voice you want.
2. Rename each pair to match the IDs above (e.g. `en_US-amy-medium.onnx` → `narrator.onnx`, `en_US-amy-medium.onnx.json` → `narrator.onnx.json`).
3. Place all files in the directory pointed to by `PIPER_VOICES_DIR` (default: `./voices`).

---

## Tests

Each phase has its own test suite. Run them in order to verify the full stack:

```bash
.venv\Scripts\python tests\check_phase1.py   # Config, models, DB
.venv\Scripts\python tests\check_phase2.py   # EPUB ingestion, Huey wiring
.venv\Scripts\python tests\check_phase3.py   # LLM pipeline
.venv\Scripts\python tests\check_phase4.py   # TTS, audio assembly, /audio endpoint
```

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

`status` transitions: `PENDING → PROCESSING → DONE` (or `FAILED`).  
`progress` goes from `0.0` to `100.0`.

### Download the audiobook

```bash
curl http://localhost:8000/books/1/audio --output audiobook.wav
```

Returns 404 until `status` is `DONE`.

### Other endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/books` | List all books |
| `DELETE` | `/books/{id}` | Delete a book and its source file |

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design reference (strategy patterns, token budgeting, job state machine).
