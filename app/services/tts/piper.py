from app.config import Settings
from app.services.tts.base import BaseTTSProvider


class PiperProvider(BaseTTSProvider):
    def __init__(self, settings: Settings) -> None:
        pass  # PIPER_VOICES_DIR and piper-tts wired in sub-task 3

    async def synthesise(self, text: str, voice_id: str) -> bytes:
        raise NotImplementedError("PiperProvider.synthesise not yet implemented")
