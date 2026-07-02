import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_VALID_LLM = frozenset({"gemini", "ollama"})
VALID_TTS_PROVIDERS = frozenset({"piper", "elevenlabs", "edgetts", "qwen"})


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


class Settings:
    def __init__(self) -> None:
        self.llm_provider: str = _require("LLM_PROVIDER")
        if self.llm_provider not in _VALID_LLM:
            raise ValueError(
                f"Invalid LLM_PROVIDER={self.llm_provider!r}. "
                f"Accepted values: {sorted(_VALID_LLM)}"
            )

        self.tts_provider: str = _require("TTS_PROVIDER")
        if self.tts_provider not in VALID_TTS_PROVIDERS:
            raise ValueError(
                f"Invalid TTS_PROVIDER={self.tts_provider!r}. "
                f"Accepted values: {sorted(VALID_TTS_PROVIDERS)}"
            )

        if self.llm_provider == "gemini":
            self.gemini_api_key: str = _require("GEMINI_API_KEY")
            self.gemini_model: str = _require("GEMINI_MODEL")

        if self.llm_provider == "ollama":
            self.ollama_base_url: str = _require("OLLAMA_BASE_URL")
            self.ollama_model: str = _require("OLLAMA_MODEL")
            self.ollama_context_tokens: int = int(_require("OLLAMA_CONTEXT_TOKENS"))
            # Budget de découpe en chunks, découplé de la fenêtre de contexte : des chunks
            # plus petits gardent la SORTIE JSON (liste d'attributions) loin de la troncature
            # et permettent un num_ctx réduit 100% GPU. Voir ARCHITECTURE.md §2.5.
            self.ollama_chunk_tokens: int = int(
                os.environ.get("OLLAMA_CHUNK_TOKENS", "4000")
            )
            self.ollama_connect_timeout: float = float(
                os.environ.get("OLLAMA_CONNECT_TIMEOUT", "60")
            )
            self.ollama_read_timeout: float = float(
                os.environ.get("OLLAMA_READ_TIMEOUT", "600")
            )
            self.ollama_timeout_per_1k_tokens: float = float(
                os.environ.get("OLLAMA_TIMEOUT_PER_1K_TOKENS", "200")
            )

        # Piper/EdgeTTS/Qwen settings are ALWAYS populated (best-effort, no _require),
        # regardless of which provider is the global default: a book can override its
        # TTS provider independently of TTS_PROVIDER (see app/services/tts/factory.py),
        # so the provider actually instantiated at generation time may not be the
        # global one. Fail-fast (ValueError) still applies below, but ONLY for the
        # provider that is actually the global default -- other providers validate
        # their own prerequisites lazily, at instantiation (see PiperProvider), with
        # a clear error instead of an AttributeError on a missing Settings attribute
        # (audit 2026-07-02, finding M1).
        self.piper_voices_dir: str | None = os.environ.get("PIPER_VOICES_DIR", "").strip() or None
        self.piper_binary_path: str | None = os.environ.get("PIPER_BINARY_PATH", "").strip() or None
        self.edgetts_locale: str = os.environ.get("EDGETTS_LOCALE", "en-US").strip() or "en-US"
        # torch/qwen-tts are optional heavy deps (requirements-qwen.txt), imported lazily
        # by the provider -- cannot fail-fast on their absence here without importing them.
        self.qwen_model: str = os.environ.get("QWEN_MODEL", "1.7b").strip() or "1.7b"
        self.qwen_language: str = os.environ.get("QWEN_LANGUAGE", "French").strip() or "French"
        self.qwen_device: str = os.environ.get("QWEN_DEVICE", "cuda:0").strip() or "cuda:0"
        self.qwen_attn: str = os.environ.get("QWEN_ATTN", "sdpa").strip() or "sdpa"

        if self.tts_provider == "piper":
            if not self.piper_voices_dir:
                raise ValueError("Missing required env var: PIPER_VOICES_DIR")
            if not Path(self.piper_voices_dir).is_dir():
                raise ValueError(
                    f"PIPER_VOICES_DIR does not exist or is not a directory: {self.piper_voices_dir!r}"
                )
            if not self.piper_binary_path:
                raise ValueError("Missing required env var: PIPER_BINARY_PATH")
            if not Path(self.piper_binary_path).is_file():
                raise ValueError(
                    f"PIPER_BINARY_PATH does not exist or is not a file: {self.piper_binary_path!r}"
                )

        if self.tts_provider == "elevenlabs":
            self.elevenlabs_api_key: str = _require("ELEVENLABS_API_KEY")

        self.database_url: str = _require("DATABASE_URL")
        self.huey_db_path: str = _require("HUEY_DB_PATH")

        _origins_raw = os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000")
        self.frontend_origins: list[str] = [
            o.strip() for o in _origins_raw.split(",") if o.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings()
