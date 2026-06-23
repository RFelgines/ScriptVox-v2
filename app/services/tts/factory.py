from app.config import Settings
from app.services.tts.base import BaseTTSProvider


def get_tts_provider(settings: Settings, override: str | None = None) -> BaseTTSProvider:
    provider = override or settings.tts_provider
    if provider == "edgetts":
        from app.services.tts.edgetts import EdgeTTSProvider
        return EdgeTTSProvider(settings)
    if provider == "elevenlabs":
        from app.services.tts.elevenlabs import ElevenLabsProvider
        return ElevenLabsProvider(settings)
    if provider == "qwen":
        from app.services.tts.qwen import QwenTTSProvider
        return QwenTTSProvider(settings)
    from app.services.tts.piper import PiperProvider
    return PiperProvider(settings)
