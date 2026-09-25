# Plugins

Drop a Python file here to add your own LLM or TTS engine — no change to ScriptVox itself.

```
plugins/
├── llm/   ← one .py file per LLM engine
└── tts/   ← one .py file per TTS engine
```

- A file whose name starts with `_` is ignored (`_example_*.py` are templates: copy one, rename it
  without the underscore).
- A broken plugin never breaks the application: it is skipped and the error is shown in
  **Settings → Plugins that failed to load**.
- Restart the API and the worker after adding or editing a plugin.
- Then pick the engine's name in **Settings** (or set `TTS_PROVIDER` / `LLM_PROVIDER` in `.env`).

Full guide: [docs/PLUGINS.md](../docs/PLUGINS.md).

> Everything in this folder except this README and the `_example_*` templates is ignored by git
> (`.gitignore`): your plugins are yours. Plugins run with the same rights as ScriptVox — only
> install code you trust.
