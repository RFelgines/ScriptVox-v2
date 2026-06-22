from app.config import Settings
from app.services.tts.base import BaseTTSProvider


def get_tts_provider(settings: Settings) -> BaseTTSProvider:
    if settings.tts_provider == "edgetts":
        from app.services.tts.edgetts import EdgeTTSProvider
        return EdgeTTSProvider(settings)
    if settings.tts_provider == "elevenlabs":
        from app.services.tts.elevenlabs import ElevenLabsProvider
        return ElevenLabsProvider(settings)
    if settings.tts_provider == "qwen":
        from app.services.tts.qwen import QwenTTSProvider
        return QwenTTSProvider(settings)
    from app.services.tts.piper import PiperProvider
    return PiperProvider(settings)
