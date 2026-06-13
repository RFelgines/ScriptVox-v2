import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_VALID_LLM = frozenset({"gemini", "ollama"})
_VALID_TTS = frozenset({"piper", "elevenlabs"})


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

        if self.tts_provider == "elevenlabs":
            self.elevenlabs_api_key: str = _require("ELEVENLABS_API_KEY")

        self.database_url: str = _require("DATABASE_URL")
        self.huey_db_path: str = _require("HUEY_DB_PATH")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings()
