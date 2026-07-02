from app.config import VALID_TTS_PROVIDERS, Settings
from app.services.tts.base import BaseTTSProvider


def get_tts_provider(settings: Settings, override: str | None = None) -> BaseTTSProvider:
    provider = override or settings.tts_provider
    if provider == "edgetts":
        from app.services.tts.edgetts import EdgeTTSProvider
        return EdgeTTSProvider(settings)
    if provider == "qwen":
        from app.services.tts.qwen import QwenTTSProvider
        return QwenTTSProvider(settings)
    if provider == "piper":
        from app.services.tts.piper import PiperProvider
        return PiperProvider(settings)
    # Any other value (e.g. a stale "elevenlabs" stored on a Book before its removal,
    # audit 2026-07-02 Lot D) used to fall through to Piper silently -- surfacing the
    # wrong voice with no error. Fail loudly instead.
    raise ValueError(
        f"Unknown tts_provider {provider!r}. Accepted values: {sorted(VALID_TTS_PROVIDERS)}"
    )
