import asyncio
import io
import wave
from pathlib import Path

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.tts.base import BaseTTSProvider


class PiperProvider(BaseTTSProvider):
    def __init__(self, settings: Settings) -> None:
        self._voices_dir = Path(settings.piper_voices_dir)

    async def synthesise(self, text: str, voice_id: str) -> bytes:
        try:
            from piper import PiperVoice  # lazy import — optional dep
        except ImportError as exc:
            raise TTSError(f"piper:{voice_id}", exc)

        model_path = self._voices_dir / f"{voice_id}.onnx"
        loop = asyncio.get_running_loop()

        try:
            voice = await loop.run_in_executor(None, PiperVoice.load, str(model_path))
        except Exception as exc:
            raise TTSError(f"piper:{voice_id}", exc)

        def _synthesize() -> bytes:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                voice.synthesize(text, wav_file)
            return buf.getvalue()

        try:
            return await loop.run_in_executor(None, _synthesize)
        except Exception as exc:
            raise TTSError(f"piper:{voice_id}", exc)
