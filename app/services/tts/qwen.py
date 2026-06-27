import array
import asyncio
import audioop
import io
import wave
from pathlib import Path

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.tts.base import BaseTTSProvider

# Logical voice_id -> Qwen3-TTS speaker preset (CustomVoice variants).
# IDs mirror VOICE_CATALOGUE (voice_assignment.py): narrator + male_N / female_N / neutral_N.
# Qwen3-TTS ships exactly 9 presets (Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden,
# Ono_Anna, Sohee) -- one per logical slot. The preset->gender mapping below is a BEST-EFFORT
# GUESS from preset naming (Qwen's docs list the names with no gender/age metadata) -- to be
# confirmed or corrected once the real-audio listening pass happens (B3 stays open until then,
# see tts-emotion-qwen3-direction memory).
_VOICE_MAP: dict[str, str] = {
    "narrator":  "Eric",
    "male_0":    "Dylan",
    "male_1":    "Ryan",
    "male_2":    "Uncle_Fu",
    "female_0":  "Vivian",
    "female_1":  "Serena",
    "female_2":  "Ono_Anna",
    "neutral_0": "Aiden",
    "neutral_1": "Sohee",
}

# CustomVoice checkpoint: preset-based synthesis + emotion via instruct.
_MODEL_IDS: dict[str, str] = {
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
}

# Base checkpoint: voice cloning via generate_voice_clone + x_vector_only_mode.
# Must NOT cohabitate with CustomVoice on a 10 Go GPU — sequential swap strategy.
_MODEL_IDS_BASE: dict[str, str] = {
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}

_MODEL_SAMPLE_RATE = 24000   # what Qwen3-TTS always returns (verified by tests/spike_qwen_tts.py)
_OUTPUT_SAMPLE_RATE = 22050  # ScriptVox's shared WAV format (assemble_wav's format guard)


def _import_qwen_deps():
    # Isolated in its own function so tests can patch it to simulate a missing install
    # without needing torch/qwen-tts to actually be absent.
    import torch
    from qwen_tts import Qwen3TTSModel
    return torch, Qwen3TTSModel


def _float_to_pcm16(samples) -> bytes:
    """Float32 audio in [-1, 1] -> 16-bit signed PCM (stdlib only, no numpy dependency)."""
    ints = [int(max(-1.0, min(1.0, float(s))) * 32767) for s in samples]
    return array.array("h", ints).tobytes()


def _resample_to_output(pcm16: bytes, source_rate: int) -> bytes:
    if source_rate == _OUTPUT_SAMPLE_RATE:
        return pcm16
    converted, _ = audioop.ratecv(pcm16, 2, 1, source_rate, _OUTPUT_SAMPLE_RATE, None)
    return converted


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit signed PCM
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _load_ref_audio(path: str):
    """Load a reference audio file and return (float32_samples, sample_rate).

    Supports .mp3 / .wav / .flac via miniaudio. Called inside run_in_executor.
    """
    import miniaudio
    import numpy as np
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext == ".mp3":
            native_sr = miniaudio.mp3_get_file_info(path).sample_rate
        elif ext == ".flac":
            native_sr = miniaudio.flac_get_file_info(path).sample_rate
        else:
            native_sr = miniaudio.wav_get_file_info(path).sample_rate
        decoded = miniaudio.decode_file(
            path,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=native_sr,
        )
    except Exception as exc:
        raise TTSError(f"qwen_clone:ref_audio:{p.name}", exc)
    samples_i16 = np.frombuffer(bytes(decoded.samples), dtype=np.int16)
    samples_f32 = samples_i16.astype(np.float32) / 32768.0
    return samples_f32, native_sr


class QwenTTSProvider(BaseTTSProvider):
    def __init__(self, settings: Settings) -> None:
        size = getattr(settings, "qwen_model", "1.7b")
        self._model_id = _MODEL_IDS.get(size, _MODEL_IDS["1.7b"])
        self._base_model_id = _MODEL_IDS_BASE.get(size, _MODEL_IDS_BASE["1.7b"])
        self._language = getattr(settings, "qwen_language", "French")
        self._device = getattr(settings, "qwen_device", "cuda:0")
        self._attn = getattr(settings, "qwen_attn", "sdpa")
        self._model = None       # CustomVoice — lazy-loaded on first preset call
        self._base_model = None  # Base — lazy-loaded on first clone call

    def resolve_voice(self, voice_id: str) -> str:
        """Return the Qwen3-TTS speaker preset for a logical voice_id."""
        speaker = _VOICE_MAP.get(voice_id)
        if speaker is None:
            raise TTSError(
                f"qwen:{voice_id}",
                ValueError(f"Unknown voice_id {voice_id!r} for Qwen3-TTS"),
            )
        return speaker

    def _ensure_model(self):
        """Load the CustomVoice model, unloading the Base model first if needed."""
        if self._model is None:
            import gc
            try:
                torch, qwen3_tts_model_cls = _import_qwen_deps()
            except ImportError as exc:
                raise TTSError(
                    "qwen:model_load",
                    ImportError(
                        "torch/qwen-tts not installed. "
                        "Run: pip install -r requirements-qwen.txt"
                    ),
                ) from exc
            if self._base_model is not None:
                self._base_model = None
                gc.collect()
                torch.cuda.empty_cache()
            self._model = qwen3_tts_model_cls.from_pretrained(
                self._model_id,
                device_map=self._device,
                dtype=torch.bfloat16,
                attn_implementation=self._attn,
            )
        return self._model

    def _ensure_base_model(self):
        """Load the Base model, unloading the CustomVoice model first if needed."""
        if self._base_model is None:
            import gc
            try:
                torch, qwen3_tts_model_cls = _import_qwen_deps()
            except ImportError as exc:
                raise TTSError(
                    "qwen:base_model_load",
                    ImportError(
                        "torch/qwen-tts not installed. "
                        "Run: pip install -r requirements-qwen.txt"
                    ),
                ) from exc
            if self._model is not None:
                self._model = None
                gc.collect()
                torch.cuda.empty_cache()
            self._base_model = qwen3_tts_model_cls.from_pretrained(
                self._base_model_id,
                device_map=self._device,
                dtype=torch.bfloat16,
                attn_implementation=self._attn,
            )
        return self._base_model

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        if reference_audio_path is not None:
            # Clone mode — Base checkpoint + generate_voice_clone
            def _run_clone() -> bytes:
                model = self._ensure_base_model()
                samples_f32, ref_sr = _load_ref_audio(reference_audio_path)
                wavs, sample_rate = model.generate_voice_clone(
                    text=text,
                    language=self._language,
                    ref_audio=(samples_f32, ref_sr),
                    x_vector_only_mode=True,
                )
                pcm16 = _float_to_pcm16(wavs[0])
                pcm16 = _resample_to_output(pcm16, sample_rate)
                return _pcm_to_wav(pcm16, _OUTPUT_SAMPLE_RATE)

            loop = asyncio.get_running_loop()
            try:
                return await loop.run_in_executor(None, _run_clone)
            except TTSError:
                raise
            except Exception as exc:
                raise TTSError(f"qwen_clone:{voice_id}", exc)

        else:
            # Preset mode — CustomVoice checkpoint + generate_custom_voice
            speaker = self.resolve_voice(voice_id)  # raises TTSError if unknown

            def _run_preset() -> bytes:
                model = self._ensure_model()
                kwargs = dict(text=text, language=self._language, speaker=speaker)
                if emotion:
                    kwargs["instruct"] = emotion
                wavs, sample_rate = model.generate_custom_voice(**kwargs)
                pcm16 = _float_to_pcm16(wavs[0])
                pcm16 = _resample_to_output(pcm16, sample_rate)
                return _pcm_to_wav(pcm16, _OUTPUT_SAMPLE_RATE)

            loop = asyncio.get_running_loop()
            try:
                return await loop.run_in_executor(None, _run_preset)
            except TTSError:
                raise
            except Exception as exc:
                raise TTSError(f"qwen:{voice_id}", exc)
