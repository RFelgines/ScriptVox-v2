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
import urllib.error
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
    if sys.version_info < (3, 11):
        warn(
            f"Python {version} — 3.11+ required",
            "download: https://www.python.org/downloads/",
        )
    elif sys.version_info >= (3, 14):
        warn(
            f"Python {version} — 3.14 is not supported yet (pinned packages ship no wheel for it)",
            "use Python 3.11 – 3.13 (3.12 recommended, see .python-version), then re-run setup",
        )
    else:
        ok(f"Python {version}")


def check_ffmpeg(env: dict[str, str]) -> None:
    configured = env.get("FFMPEG_PATH", "")
    if (configured and Path(configured).is_file()) or shutil.which("ffmpeg"):
        ok("ffmpeg found (chaptered M4B audiobook export enabled)")
    else:
        info(
            "ffmpeg not found — the MP3 is still produced, but the chaptered M4B export is disabled. "
            "Install ffmpeg (https://ffmpeg.org/download.html) or set FFMPEG_PATH in .env"
        )


def plugin_names(kind: str, env: dict[str, str]) -> list[str]:
    """Plugin file names (without importing them) — enough to recognise a custom provider."""
    raw = env.get("PLUGINS_DIR", "plugins") or "plugins"
    folder = Path(raw) if Path(raw).is_absolute() else ROOT / raw
    folder = folder / kind
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.py") if not p.name.startswith("_"))


def http_reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True  # the server answered (e.g. 401/404 on this path) — it is up
    except Exception:
        return False


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


def check_gemini(api_key: str, model: str = "") -> None:
    if model.startswith("gemini-2."):
        warn(
            f"GEMINI_MODEL={model!r} is retired or about to be (2.0 shut down 2026-06-01, 2.5 on 2026-10-16)",
            "pick a current model in Settings (or list them with client.models.list()), e.g. gemini-3.1-flash-lite",
        )
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
    plugins = plugin_names("llm", env)
    if provider == "ollama":
        ok("LLM_PROVIDER=ollama (fully local)")
        check_ollama(env.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    elif provider == "gemini":
        ok("LLM_PROVIDER=gemini (cloud, fastest to set up)")
        check_gemini(env.get("GEMINI_API_KEY", ""), env.get("GEMINI_MODEL", ""))
    elif provider == "openai_compatible":
        base = env.get("OPENAI_BASE_URL", "http://localhost:1234/v1")
        ok("LLM_PROVIDER=openai_compatible (any OpenAI-API server)")
        if not env.get("OPENAI_MODEL"):
            warn("OPENAI_MODEL is empty", "set the model name your server exposes (see Settings > Models)")
        if http_reachable(base.rstrip("/") + "/models"):
            ok(f"server reachable at {base}")
        else:
            warn(f"server not reachable at {base}", "start LM Studio / llama-server / vLLM, or fix OPENAI_BASE_URL")
    elif provider and provider in plugins:
        ok(f"LLM_PROVIDER={provider} (plugin plugins/llm/{provider}.py)")
    elif provider:
        warn(
            f"LLM_PROVIDER={provider!r} is not a recognised value "
            f"(ollama | gemini | openai_compatible{' | ' + ' | '.join(plugins) if plugins else ''})"
        )
    else:
        warn(
            "LLM_PROVIDER not set",
            "edit .env — set LLM_PROVIDER=gemini (+ GEMINI_API_KEY) for the fastest path,",
            "or LLM_PROVIDER=ollama for a fully local setup (see README Quick start).",
        )


def check_qwen_gpu() -> None:
    """Runs torch in the project's own venv (never imported in this stdlib-only script)."""
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python = str(venv_python if venv_python.exists() else sys.executable)
    code = (
        "import torch;"
        "print(torch.cuda.is_available(), getattr(torch.version, 'hip', None), "
        "torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
    )
    try:
        out = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        warn(f"could not run the GPU check: {exc}")
        return
    if out.returncode != 0:
        warn(
            "PyTorch is not installed in the project's Python",
            "NVIDIA: pip install torch --index-url https://download.pytorch.org/whl/cu128",
            "AMD Radeon: install PyTorch for ROCm (see requirements-qwen.txt), NOT the CUDA build",
            "then: pip install -r requirements-qwen.txt",
        )
        return
    available, hip, name = (out.stdout.strip().split(" ", 2) + ["", ""])[:3]
    if available != "True":
        warn(
            "PyTorch is installed but sees no GPU (torch.cuda.is_available() is False)",
            "AMD Radeon: this is what a CUDA build of PyTorch does — install the ROCm build (requirements-qwen.txt)",
            "NVIDIA: check the driver / CUDA version matching your torch build",
        )
    else:
        backend = f"ROCm/HIP {hip}" if hip and hip != "None" else "CUDA"
        ok(f"GPU visible to PyTorch via {backend}: {name.strip()}")
        if hip and hip != "None":
            info("AMD tip: keep QWEN_ATTN=sdpa; if the driver resets, set TORCH_BLAS_PREFER_HIPBLASLT=0")


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
        ok("TTS_PROVIDER=qwen (local GPU)")
        check_qwen_gpu()
    elif provider == "openai_tts":
        base = env.get("TTS_HTTP_BASE_URL", "http://localhost:8880/v1")
        ok("TTS_PROVIDER=openai_tts (any /v1/audio/speech server)")
        if http_reachable(base):
            ok(f"server reachable at {base}")
        else:
            warn(f"server not reachable at {base}", "start your TTS server or fix TTS_HTTP_BASE_URL")
    elif provider == "command":
        command = env.get("TTS_COMMAND", "")
        if not command:
            warn("TTS_PROVIDER=command but TTS_COMMAND is empty", "see .env.example for the placeholders")
        else:
            exe = command.split()[0].strip('"')
            if shutil.which(exe) or Path(exe).is_file():
                ok(f"TTS_PROVIDER=command, executable found: {exe}")
            else:
                warn(f"TTS_COMMAND executable not found: {exe}")
    elif provider in plugin_names("tts", env):
        ok(f"TTS_PROVIDER={provider} (plugin plugins/tts/{provider}.py)")
    else:
        extra = plugin_names("tts", env)
        warn(
            f"TTS_PROVIDER={provider!r} is not a recognised value "
            f"(edgetts | piper | qwen | openai_tts | command{' | ' + ' | '.join(extra) if extra else ''})"
        )


def main() -> int:
    print("=== ScriptVox environment check ===")
    check_python()
    check_node()
    check_venv()
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
        check_ffmpeg(env)

    print()
    if warnings:
        print(f"Summary: {len(warnings)} item(s) need attention (see [!!] above).")
        return 1
    print("Summary: everything looks ready. Next: ./start.sh (or start.ps1 on Windows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
