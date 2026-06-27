import asyncio
import subprocess
import tempfile
from pathlib import Path

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.tts.base import BaseTTSProvider


class PiperProvider(BaseTTSProvider):
    def __init__(self, settings: Settings) -> None:
        # Resolve to absolute so synthesis is independent of the worker's cwd.
        # piper.exe locates its DLLs and espeak-ng-data relative to its own path.
        self._voices_dir = Path(settings.piper_voices_dir).resolve()
        self._binary = Path(settings.piper_binary_path).resolve()

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        # emotion and reference_audio_path accepted for interface parity but ignored (Piper has no emotion/clone control).
        # Piper reads its config from "<model>.onnx.json" automatically.
        model_path = self._voices_dir / f"{voice_id}.onnx"

        def _run() -> bytes:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                result = subprocess.run(
                    [str(self._binary), "--model", str(model_path),
                     "--output_file", str(tmp_path)],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    err = result.stderr.decode("utf-8", errors="replace").strip()
                    raise RuntimeError(
                        f"piper exited with code {result.returncode}: {err or '<no stderr>'}"
                    )
                return tmp_path.read_bytes()
            finally:
                tmp_path.unlink(missing_ok=True)

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _run)
        except Exception as exc:
            raise TTSError(f"piper:{voice_id}", exc)
