# Adding your own models and engines

ScriptVox never hard-codes *which* model you use. There are four levels, from "change a name" to
"write an engine". Start at the top and go down only if you need to.

| # | You want to… | Do this | Code needed |
|---|---|---|---|
| 1 | use another **model** on an engine ScriptVox knows | type its name in **Settings → Models** | none |
| 2 | use a model served over the **OpenAI API** (LM Studio, llama.cpp, vLLM, OpenRouter, Kokoro-FastAPI…) | `openai_compatible` (LLM) / `openai_tts` (TTS) | none |
| 3 | use a **command-line program** as the voice | `TTS_PROVIDER=command` + `TTS_COMMAND` | none |
| 4 | use a **Python library / custom API** | write a **plugin** | one small file |

> Restart the API **and** the worker after changing `.env` or a plugin. Settings values apply to the
> next analysis / generation.

---

## 1. Any model name (no code)

*Settings → Models* has one block for the analysis LLM and one for the voices. Choose the engine, then
either pick from the list (installed Ollama models, models reported by the server, Qwen presets…) or
**type any name**. A name that is not in the list is accepted and sent to the engine as is.

Values saved in *Settings* override `.env`; an empty field means "use `.env`". Fields per engine:

| Engine | Fields |
|---|---|
| `ollama` | model, server address |
| `openai_compatible` | model, server address (API key: `OPENAI_API_KEY` in `.env`) |
| `gemini` | model (key: `GEMINI_API_KEY`) |
| `qwen` | model = `1.7b` / `0.6b` / **any Hugging Face id or local path** of a compatible checkpoint; cloning model |
| `edgetts` | voice language (`fr-FR`, `en-GB`…) |
| `openai_tts` | model, server address |
| plugin | model (+ whatever the plugin reads from `options`) |

API keys and the external command are **never** editable from the web interface (secrets and code
execution stay in `.env`).

---

## 2. OpenAI-compatible servers

### LLM — `openai_compatible`

```ini
LLM_PROVIDER=openai_compatible
OPENAI_BASE_URL=http://localhost:1234/v1     # LM Studio's default; llama-server: http://localhost:8080/v1
OPENAI_MODEL=qwen3.8-27b                     # the name the server exposes (GET /v1/models)
OPENAI_API_KEY=                              # empty for local servers
```

The provider asks for a JSON-Schema-constrained answer and falls back automatically to
`json_object`, then to plain text, if the server refuses. Chunk size: `OPENAI_CHUNK_TOKENS`.

### TTS — `openai_tts`

```ini
TTS_PROVIDER=openai_tts
TTS_HTTP_BASE_URL=http://localhost:8880/v1        # POST {base}/audio/speech
TTS_HTTP_MODEL=kokoro
TTS_HTTP_VOICE_MAP={"narrator":"ff_siwis","male_0":"am_adam","default":"ff_siwis"}
TTS_HTTP_EXTRA_BODY={"speed":0.95}
TTS_HTTP_EMOTION_FIELD=                            # body field receiving the per-line emotion, if any
TTS_HTTP_CONCURRENCY=1
```

ScriptVox's logical voices are `narrator`, `male_0`–`male_2`, `female_0`–`female_2`, `neutral_0`–`neutral_1`
(plus your cloned voices). `TTS_HTTP_VOICE_MAP` maps them to the server's voice names; `"default"`
covers every unmapped id. The server may answer WAV, MP3, FLAC or OGG at any rate. This engine does not
clone voices (cloned voices need `qwen` or a plugin).

---

## 3. An external program — `command`

```ini
TTS_PROVIDER=command
TTS_COMMAND=python C:/tts/run.py --in {text_file} --out {out} --voice {voice} --lang {language}
TTS_COMMAND_VOICE_MAP={"narrator":"anna","default":"marc"}
TTS_COMMAND_TIMEOUT=300
```

Placeholders (replaced in each argument): `{text_file}` (UTF-8 file holding the text), `{text}` (the
text itself), `{out}` (file the program must write), `{voice}`, `{emotion}`, `{ref}` (reference audio for
a cloned voice, else empty), `{language}` (`fr`, `en`…). If the command has no `{out}`, the audio is read
from the program's standard output. Exit code ≠ 0 is an error (its stderr is shown).

The command is split like a shell would, then **run directly — no shell** — so nothing in a book can
inject a command. It is defined in `.env` only.

---

## 4. Write a plugin

A plugin is one Python file dropped in `plugins/tts/` or `plugins/llm/`. Copy a template
(`plugins/tts/_example_tts.py`, `plugins/llm/_example_llm.py`), rename it **without the leading
underscore**, edit, restart. The engine then appears in *Settings*.

### TTS plugin

```python
from app.services.audio.format import silence_wav
from app.services.tts.base import BaseTTSProvider

PROVIDER_NAME = "my_engine"            # [a-z0-9_]+, not an official name
DESCRIPTION = "Shown in Settings"       # optional

def list_models(settings, options):     # optional: suggestions for the Model field
    return ["model-a", "model-b"]

class MyEngine(BaseTTSProvider):
    supports_concurrency = 1            # simultaneous calls (1 = sequential, e.g. local GPU)
    max_chars = 500                     # longer texts are split at sentence ends
    keep_loaded = False                 # True = keep the instance (loaded model) between chapters

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        ...                             # return WAV / MP3 / FLAC / OGG bytes, any sample rate
        return silence_wav(500)

    def unload(self) -> None:           # optional: free VRAM
        ...

def create(settings, options, language=None):
    return MyEngine()
```

- `options` holds the Settings values (`model`, `base_url`, `locale`, `base_model`); `settings` is the
  application `Settings` (all `.env` values, e.g. `settings.qwen_device`).
- `language` is the book's language (`"fr"`, `"en-US"`…) or `None`.
- `emotion` is the model's free-text description of how the line should be delivered
  (`"furious and panicked"`); map it to whatever your engine understands, or ignore it.
- A blocking library call must run in a thread:
  `await asyncio.get_running_loop().run_in_executor(None, fn)`.
- Raise `app.core.exceptions.TTSError(context, cause)` for a failure — the pipeline retries 3 times, then
  marks the chapter failed with your message.
- Return audio in **any** decodable format. For float samples use `float_to_pcm16` and `pcm16_to_wav`
  from `app.services.audio.format`.
- With `keep_loaded = True` the worker keeps your instance (and its loaded model) alive across chapters
  and calls `unload()` after `TTS_IDLE_UNLOAD_SECONDS` of inactivity, on *Settings → Free GPU memory*,
  and before an LLM analysis.

### LLM plugin

The pipeline pre-segments the chapter, sends numbered spans to the model and repairs its answer
deterministically; a plugin only has to **call the model** and return its JSON text:

```python
from app.services.llm.base import (ANALYSIS_JSON_SCHEMA, BaseLLMProvider, SYSTEM_PROMPT,
                                   _build_user_prompt, _parse_llm_json, _pre_segment)
from app.services.llm.language_profiles import resolve_profile
```

See `plugins/llm/_example_llm.py` for the complete template (analysis + merge suggestions).
`chunk_tokens` sets the per-call budget; `unload()` (optional) is called at the end of an analysis.

### Rules and safety

- A file starting with `_` is ignored. Names clashing with an official engine are refused.
- A plugin that fails to import, lacks `PROVIDER_NAME` / `create`, or clashes is **skipped**; the reason is
  displayed in *Settings → Plugins that failed to load*. It never breaks the application.
- **Plugins run with the same rights as ScriptVox.** Only install code you trust. Your plugins are ignored
  by git (`.gitignore`) — only the READMEs and `_example_*` templates are tracked.

### Compare engines by ear

```bash
python scripts/bench_tts.py --provider my_engine --model model-a
python scripts/bench_tts.py --provider qwen --model 0.6b
```

renders the same French script (`tests/listening/fr_script.txt`) with each engine into
`data_test/listening/<engine>/` and prints the real-time factor.
