import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Providers OFFICIELS (fournis avec l'application). Les plugins déposés dans plugins/ s'y
# ajoutent dynamiquement : pour la liste complète, utiliser
# app.services.registry.llm_provider_names() / tts_provider_names().
VALID_LLM_PROVIDERS = frozenset({"gemini", "ollama", "openai_compatible"})
# "elevenlabs" retiré (2026-07-02, audit finding M2) : le provider n'a jamais pu
# fonctionner (voice_id logiques du catalogue injectés tels quels dans une API qui
# attend un UUID ElevenLabs, modèle codé en dur anglais-only) et n'était couvert par
# aucun test réel. Voir mémoire audit-2026-07-02-remediation-plan, Lot D.
VALID_TTS_PROVIDERS = frozenset({"piper", "edgetts", "qwen", "openai_tts", "command"})


def _json_env(name: str) -> dict:
    """Variable d'environnement contenant un objet JSON (ex. table de voix). {} si absente."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} n'est pas un JSON valide : {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} doit être un objet JSON (ex. {{\"narrator\": \"voix\"}})")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "oui")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


class Settings:
    def __init__(self) -> None:
        from app.services import registry  # import local : registry ne dépend pas de config

        self.llm_provider: str = _require("LLM_PROVIDER")
        if self.llm_provider not in registry.llm_provider_names():
            raise ValueError(
                f"Invalid LLM_PROVIDER={self.llm_provider!r}. "
                f"Accepted values: {registry.llm_provider_names()}"
            )

        self.tts_provider: str = _require("TTS_PROVIDER")
        if self.tts_provider not in registry.tts_provider_names():
            raise ValueError(
                f"Invalid TTS_PROVIDER={self.tts_provider!r}. "
                f"Accepted values: {registry.tts_provider_names()}"
            )

        # Gemini settings — always populated (best-effort, no _require), regardless
        # of which LLM provider is the global default: AppSetting.preferred_llm_provider
        # can switch to Gemini at runtime even when .env default is Ollama.
        # Fail-fast (ValueError) only when Gemini IS the global default.
        self.gemini_api_key: str | None = os.environ.get("GEMINI_API_KEY", "").strip() or None
        self.gemini_model: str | None = os.environ.get("GEMINI_MODEL", "").strip() or None
        if self.llm_provider == "gemini":
            if not self.gemini_api_key:
                raise ValueError("Missing required env var: GEMINI_API_KEY")
            if not self.gemini_model:
                raise ValueError("Missing required env var: GEMINI_MODEL")

        # Ollama settings — always populated (best-effort), fail-fast only when
        # Ollama is the global default. Budget de découpe en chunks, découplé de la
        # fenêtre de contexte : des chunks plus petits gardent la SORTIE JSON loin
        # de la troncature. Voir ARCHITECTURE.md §2.5.
        self.ollama_base_url: str | None = os.environ.get("OLLAMA_BASE_URL", "").strip() or None
        self.ollama_model: str | None = os.environ.get("OLLAMA_MODEL", "").strip() or None
        _ctx_raw = os.environ.get("OLLAMA_CONTEXT_TOKENS", "").strip()
        self.ollama_context_tokens: int | None = int(_ctx_raw) if _ctx_raw else None
        self.ollama_chunk_tokens: int = int(
            os.environ.get("OLLAMA_CHUNK_TOKENS", "4000") or "4000"
        )
        self.ollama_connect_timeout: float = float(
            os.environ.get("OLLAMA_CONNECT_TIMEOUT", "60") or "60"
        )
        self.ollama_read_timeout: float = float(
            os.environ.get("OLLAMA_READ_TIMEOUT", "600") or "600"
        )
        self.ollama_timeout_per_1k_tokens: float = float(
            os.environ.get("OLLAMA_TIMEOUT_PER_1K_TOKENS", "200") or "200"
        )
        if self.llm_provider == "ollama":
            if not self.ollama_base_url:
                raise ValueError("Missing required env var: OLLAMA_BASE_URL")
            if not self.ollama_model:
                raise ValueError("Missing required env var: OLLAMA_MODEL")
            if not self.ollama_context_tokens:
                raise ValueError("Missing required env var: OLLAMA_CONTEXT_TOKENS")

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

        # ── Réglages transverses LLM ─────────────────────────────────────────────
        self.llm_temperature: float = float(os.environ.get("LLM_TEMPERATURE", "0.2") or "0.2")
        # Libère la VRAM d'Ollama à la fin de l'analyse (le TTS local en a besoin).
        self.llm_unload_after_analysis: bool = _bool_env("LLM_UNLOAD_AFTER_ANALYSIS", True)

        # ── Serveur LLM compatible OpenAI (LM Studio, llama.cpp, vLLM, OpenRouter…) ─
        self.openai_base_url: str = (
            os.environ.get("OPENAI_BASE_URL", "").strip() or "http://localhost:1234/v1"
        )
        self.openai_api_key: str | None = os.environ.get("OPENAI_API_KEY", "").strip() or None
        self.openai_model: str | None = os.environ.get("OPENAI_MODEL", "").strip() or None
        self.openai_chunk_tokens: int = int(os.environ.get("OPENAI_CHUNK_TOKENS", "12000") or "12000")
        self.openai_timeout: float = float(os.environ.get("OPENAI_TIMEOUT", "900") or "900")
        if self.llm_provider == "openai_compatible" and not self.openai_model:
            raise ValueError("Missing required env var: OPENAI_MODEL")

        # ── TTS générique : serveur compatible OpenAI (/v1/audio/speech) ─────────
        self.tts_http_base_url: str = (
            os.environ.get("TTS_HTTP_BASE_URL", "").strip() or "http://localhost:8880/v1"
        )
        self.tts_http_api_key: str | None = os.environ.get("TTS_HTTP_API_KEY", "").strip() or None
        self.tts_http_model: str = os.environ.get("TTS_HTTP_MODEL", "").strip() or "tts-1"
        self.tts_http_voice_map: dict = _json_env("TTS_HTTP_VOICE_MAP")
        self.tts_http_extra_body: dict = _json_env("TTS_HTTP_EXTRA_BODY")
        self.tts_http_emotion_field: str | None = (
            os.environ.get("TTS_HTTP_EMOTION_FIELD", "").strip() or None
        )
        self.tts_http_concurrency: int = int(os.environ.get("TTS_HTTP_CONCURRENCY", "1") or "1")
        # ── TTS OmniVoice : serveur local scripts/omnivoice_server.py (venv séparé) ──
        self.omnivoice_url: str = (
            os.environ.get("OMNIVOICE_URL", "").strip() or "http://127.0.0.1:8770"
        )
        self.omnivoice_num_step: int | None = (
            int(os.environ["OMNIVOICE_NUM_STEP"]) if os.environ.get("OMNIVOICE_NUM_STEP", "").strip() else None
        )
        self.omnivoice_timeout: float = float(os.environ.get("OMNIVOICE_TIMEOUT", "600") or "600")
        self.omnivoice_voice_map: dict = _json_env("OMNIVOICE_VOICE_MAP")
        # ── TTS générique : programme externe. Défini UNIQUEMENT ici (jamais modifiable via
        # l'API : exécuter une commande choisie par une requête HTTP serait une faille).
        self.tts_command: str | None = os.environ.get("TTS_COMMAND", "").strip() or None
        self.tts_command_timeout: float = float(os.environ.get("TTS_COMMAND_TIMEOUT", "300") or "300")
        self.tts_command_voice_map: dict = _json_env("TTS_COMMAND_VOICE_MAP")
        if self.tts_provider == "command" and not self.tts_command:
            raise ValueError("Missing required env var: TTS_COMMAND")

        # ── Surcharges de tables de voix / checkpoints (moteurs officiels) ────────
        self.edgetts_voice_map: dict = _json_env("EDGETTS_VOICE_MAP")
        self.qwen_voice_map: dict = _json_env("QWEN_VOICE_MAP")
        self.qwen_base_model: str | None = os.environ.get("QWEN_BASE_MODEL", "").strip() or None

        # ── Assemblage audio ─────────────────────────────────────────────────────
        self.pause_same_voice_ms: int = int(os.environ.get("AUDIO_PAUSE_SAME_VOICE_MS", "250") or "250")
        self.pause_voice_change_ms: int = int(os.environ.get("AUDIO_PAUSE_VOICE_CHANGE_MS", "450") or "450")
        self.pause_chapter_ms: int = int(os.environ.get("AUDIO_PAUSE_CHAPTER_MS", "1500") or "1500")
        self.audio_normalize: bool = _bool_env("AUDIO_NORMALIZE", True)
        # 0 = valeur propre au provider ; sinon force max_chars / concurrence pour tous.
        self.tts_max_chars: int = int(os.environ.get("TTS_MAX_CHARS", "0") or "0")
        self.tts_concurrency: int = int(os.environ.get("TTS_CONCURRENCY", "0") or "0")
        # Secondes d'inactivité avant déchargement d'un modèle TTS gardé en mémoire (0 = jamais).
        self.tts_idle_unload_seconds: int = int(os.environ.get("TTS_IDLE_UNLOAD_SECONDS", "300") or "300")
        self.ffmpeg_path: str | None = os.environ.get("FFMPEG_PATH", "").strip() or None

        self.database_url: str = _require("DATABASE_URL")
        self.huey_db_path: str = _require("HUEY_DB_PATH")
        # Obligatoire (pas de défaut silencieux vers "data") : un test qui oublierait de
        # le définir écrirait dans le vrai dossier data/ de l'application (incident réel
        # 2026-07-02 -- perte de couverture + audio TTS de plusieurs chapitres réels).
        self.data_dir: str = _require("DATA_DIR")

        _origins_raw = os.environ.get(
            "FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        )
        self.frontend_origins: list[str] = [
            o.strip() for o in _origins_raw.split(",") if o.strip()
        ]
        # Noms d'hôte acceptés dans l'en-tête Host (défense contre le DNS rebinding).
        # "testserver" = hôte du TestClient Starlette (nom à un seul label, non résoluble
        # par un attaquant vers 127.0.0.1).
        _hosts_raw = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
        self.allowed_hosts: list[str] = [h.strip() for h in _hosts_raw.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings()
