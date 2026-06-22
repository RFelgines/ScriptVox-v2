import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_VALID_LLM = frozenset({"gemini", "ollama"})
_VALID_TTS = frozenset({"piper", "elevenlabs", "edgetts", "qwen"})


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
        if self.tts_provider not in _VALID_TTS:
            raise ValueError(
                f"Invalid TTS_PROVIDER={self.tts_provider!r}. "
                f"Accepted values: {sorted(_VALID_TTS)}"
            )

        if self.llm_provider == "gemini":
            self.gemini_api_key: str = _require("GEMINI_API_KEY")
            self.gemini_model: str = _require("GEMINI_MODEL")

        if self.llm_provider == "ollama":
            self.ollama_base_url: str = _require("OLLAMA_BASE_URL")
            self.ollama_model: str = _require("OLLAMA_MODEL")
            self.ollama_context_tokens: int = int(_require("OLLAMA_CONTEXT_TOKENS"))
            self.ollama_connect_timeout: float = float(
                os.environ.get("OLLAMA_CONNECT_TIMEOUT", "60")
            )
            self.ollama_read_timeout: float = float(
                os.environ.get("OLLAMA_READ_TIMEOUT", "600")
            )

        if self.tts_provider == "piper":
            self.piper_voices_dir: str = _require("PIPER_VOICES_DIR")
            if not Path(self.piper_voices_dir).is_dir():
                raise ValueError(
                    f"PIPER_VOICES_DIR does not exist or is not a directory: {self.piper_voices_dir!r}"
                )
            self.piper_binary_path: str = _require("PIPER_BINARY_PATH")
            if not Path(self.piper_binary_path).is_file():
                raise ValueError(
                    f"PIPER_BINARY_PATH does not exist or is not a file: {self.piper_binary_path!r}"
                )

        if self.tts_provider == "edgetts":
            self.edgetts_locale: str = (
                os.environ.get("EDGETTS_LOCALE", "en-US").strip() or "en-US"
            )

        if self.tts_provider == "elevenlabs":
            self.elevenlabs_api_key: str = _require("ELEVENLABS_API_KEY")

        if self.tts_provider == "qwen":
            # torch/qwen-tts are optional heavy deps (requirements-qwen.txt), imported lazily
            # by the provider -- cannot fail-fast on their absence here without importing them.
            self.qwen_model: str = os.environ.get("QWEN_MODEL", "1.7b").strip() or "1.7b"
            self.qwen_language: str = os.environ.get("QWEN_LANGUAGE", "French").strip() or "French"
            self.qwen_device: str = os.environ.get("QWEN_DEVICE", "cuda:0").strip() or "cuda:0"
            self.qwen_attn: str = os.environ.get("QWEN_ATTN", "sdpa").strip() or "sdpa"

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
