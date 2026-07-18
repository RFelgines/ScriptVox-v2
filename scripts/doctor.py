"""Environment preflight for ScriptVox.

Read-only: detects what's present/missing and prints the exact command to run
for whatever is missing. Never installs anything itself (no sudo, no silent
`ollama pull`, no npm/pip calls) — installing system-level tools or pulling a
multi-GB model is a decision the user should make deliberately.

Standard library only, so it runs even before setup.sh/setup.ps1 has done
anything (e.g. `python3 scripts/doctor.py` with a bare system Python).
"""

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OK = "[OK]  "
WARN = "[!!]  "
INFO = "[--]  "

warnings = []


def ok(msg: str) -> None:
    print(OK + msg)


def warn(msg: str, *fix_lines: str) -> None:
    print(WARN + msg)
    for line in fix_lines:
        print("        " + line)
    warnings.append(msg)


def info(msg: str) -> None:
    print(INFO + msg)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def check_python() -> None:
    version = sys.version.split()[0]
    if sys.version_info >= (3, 11):
        ok(f"Python {version}")
    else:
        warn(
            f"Python {version} — 3.11+ recommended",
            "download: https://www.python.org/downloads/",
        )


def check_node() -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node and npm:
        node_v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        npm_v = subprocess.run([npm, "--version"], capture_output=True, text=True).stdout.strip()
        ok(f"Node {node_v} / npm {npm_v}")
    else:
        warn(
            "Node.js / npm not found on PATH",
            "install: https://nodejs.org/ (LTS)",
        )


def check_venv() -> bool:
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if venv_python.exists():
        ok(".venv present")
        return True
    warn(
        ".venv missing",
        "run: ./setup.sh (or setup.ps1 on Windows)",
    )
    return False


def check_frontend_deps() -> None:
    if (ROOT / "frontend" / "node_modules").is_dir():
        ok("frontend/node_modules present")
    else:
        warn(
            "frontend/node_modules missing",
            "run: ./setup.sh (or setup.ps1 on Windows)",
        )


def check_ollama(base_url: str) -> None:
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3):
            ok(f"Ollama reachable at {base_url}")
    except Exception:
        warn(
            f"Ollama not reachable at {base_url}",
            "install: https://ollama.com/download",
            "then:    ollama pull qwen3:1.7b   (or whatever OLLAMA_MODEL is set to)",
            "verify:  curl " + base_url.rstrip("/") + "/api/tags",
        )


def check_gemini(api_key: str) -> None:
    if api_key and api_key != "your_gemini_api_key_here":
        ok("GEMINI_API_KEY set")
    else:
        warn(
            "GEMINI_API_KEY missing or still the placeholder value",
            "get a key: https://aistudio.google.com/apikey",
            "then set GEMINI_API_KEY=... in .env",
        )


def check_llm_provider(env: dict[str, str]) -> None:
    provider = env.get("LLM_PROVIDER", "")
    if provider == "ollama":
        ok("LLM_PROVIDER=ollama (fully local)")
        check_ollama(env.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    elif provider == "gemini":
        ok("LLM_PROVIDER=gemini (cloud, fastest to set up)")
        check_gemini(env.get("GEMINI_API_KEY", ""))
    elif provider:
        warn(f"LLM_PROVIDER={provider!r} is not a recognised value (ollama | gemini)")
    else:
        warn(
            "LLM_PROVIDER not set",
            "edit .env — set LLM_PROVIDER=gemini (+ GEMINI_API_KEY) for the fastest path,",
            "or LLM_PROVIDER=ollama for a fully local setup (see README Quick start).",
        )


def check_tts_provider(env: dict[str, str]) -> None:
    provider = env.get("TTS_PROVIDER", "edgetts")
    if provider == "edgetts":
        ok("TTS_PROVIDER=edgetts (no local setup needed, just internet)")
    elif provider == "piper":
        voices_dir = env.get("PIPER_VOICES_DIR", "")
        binary = env.get("PIPER_BINARY_PATH", "")
        if voices_dir and Path(voices_dir).is_dir() and binary and Path(binary).is_file():
            ok("TTS_PROVIDER=piper, voices dir and binary found")
        else:
            warn(
                "TTS_PROVIDER=piper but PIPER_VOICES_DIR/PIPER_BINARY_PATH missing or invalid",
                "download the binary: https://github.com/rhasspy/piper/releases",
                "see README > Piper binary (local TTS)",
            )
    elif provider == "qwen":
        info("TTS_PROVIDER=qwen — GPU-only, requires `pip install -r requirements-qwen.txt` (not checked here)")
    else:
        warn(f"TTS_PROVIDER={provider!r} is not a recognised value (edgetts | piper | qwen)")


def main() -> int:
    print("=== ScriptVox environment check ===")
    check_python()
    check_node()
    has_venv = check_venv()
    check_frontend_deps()

    env_path = ROOT / ".env"
    if not env_path.is_file():
        warn(
            ".env missing",
            "run: ./setup.sh (or setup.ps1 on Windows), or copy .env.example to .env yourself",
        )
    else:
        ok(".env present")
        env = parse_env_file(env_path)
        check_llm_provider(env)
        check_tts_provider(env)

    print()
    if warnings:
        print(f"Summary: {len(warnings)} item(s) need attention (see [!!] above).")
        return 1
    print("Summary: everything looks ready. Next: ./start.sh (or start.ps1 on Windows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
