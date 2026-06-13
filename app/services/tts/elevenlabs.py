from app.config import Settings
from app.services.tts.base import BaseTTSProvider


class ElevenLabsProvider(BaseTTSProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.elevenlabs_api_key

    async def synthesise(self, text: str, voice_id: str) -> bytes:
        raise NotImplementedError("ElevenLabsProvider.synthesise not yet implemented")
