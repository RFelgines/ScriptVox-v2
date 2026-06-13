from app.config import Settings
from app.services.tts.base import BaseTTSProvider


def get_tts_provider(settings: Settings) -> BaseTTSProvider:
    if settings.tts_provider == "elevenlabs":
        from app.services.tts.elevenlabs import ElevenLabsProvider
        return ElevenLabsProvider(settings)
    from app.services.tts.piper import PiperProvider
    return PiperProvider(settings)
