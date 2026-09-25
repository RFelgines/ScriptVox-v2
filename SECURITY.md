# Security policy

ScriptVox is a **local, single-user tool**: no accounts, no authentication. Run it on your own
machine and keep it on `localhost` (the `start.*` scripts bind to `127.0.0.1`). Do **not** expose the
API or the frontend to the internet or an untrusted network.

## What the application defends against

- **Cross-site requests from your browser**: writes (POST/PATCH/DELETE) are refused unless their `Origin`
  is in `FRONTEND_ORIGINS`.
- **DNS rebinding**: requests whose `Host` is not in `ALLOWED_HOSTS` are rejected.
- **Malicious EPUBs**: 200 MB upload cap; decompression-bomb checks (uncompressed size, file count,
  compression ratio); `lxml >= 5`.
- **Command injection**: the external-command TTS engine is configurable only from `.env`, runs
  without a shell, and receives the book's text through a file or a single argument.
- **Path traversal**: files are stored under generated names; client file names are never used in paths.

## What it does not defend against

- Anyone who can reach the API port from the network (there is no login).
- Malicious **plugins** (they run with the application's rights).
- Cloud engines seeing your text (Gemini, EdgeTTS) — pick local engines for confidential books.

## Reporting a vulnerability

Please open a **private** security advisory on GitHub
(*Security → Report a vulnerability* on the repository) rather than a public issue. Include the
version (commit), the configuration involved and steps to reproduce.
