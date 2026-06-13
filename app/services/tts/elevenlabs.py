import io
import wave

import httpx

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.tts.base import BaseTTSProvider

_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_PCM_SAMPLE_RATE = 22050


class ElevenLabsProvider(BaseTTSProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.elevenlabs_api_key

    async def synthesise(self, text: str, voice_id: str) -> bytes:
        url = _API_URL.format(voice_id=voice_id)
        headers = {"xi-api-key": self._api_key}
        params = {"output_format": f"pcm_{_PCM_SAMPLE_RATE}"}
        body = {"text": text, "model_id": "eleven_monolingual_v1"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body, params=params, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise TTSError(f"elevenlabs:{voice_id}", exc)

        return _pcm_to_wav(resp.content)


def _pcm_to_wav(pcm: bytes, sample_rate: int = _PCM_SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit PCM
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()
