import io
import wave

import edge_tts
import miniaudio

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.llm.language_profiles import resolve_profile
from app.services.tts.base import BaseTTSProvider

# Logical voice_id -> EdgeTTS neural voice name, keyed by BCP-47 locale.
# IDs mirror VOICE_CATALOGUE (voice_assignment.py): narrator + male_N / female_N / neutral_N.
# fr-FR only has 2 distinct male / 3 distinct female neural voices (checked live
# via edge_tts.list_voices()), so some slots must repeat one. male_0 deliberately
# avoids reusing the narrator voice (Henri) -- it's the first slot filled by the
# scorer, so the repeat is pushed to male_1/male_2 instead, where it's less often
# heard right next to narration.
_VOICE_MAP: dict[str, dict[str, str]] = {
    "en-US": {
        "narrator":  "en-US-ChristopherNeural",
        "male_0":    "en-US-GuyNeural",
        "male_1":    "en-US-EricNeural",
        "male_2":    "en-US-RogerNeural",
        "female_0":  "en-US-JennyNeural",
        "female_1":  "en-US-AriaNeural",
        "female_2":  "en-US-MichelleNeural",
        "neutral_0": "en-US-AndrewNeural",
        "neutral_1": "en-US-BrianNeural",
    },
    "fr-FR": {
        "narrator":  "fr-FR-HenriNeural",
        "male_0":    "fr-FR-RemyMultilingualNeural",
        "male_1":    "fr-FR-HenriNeural",
        "male_2":    "fr-FR-HenriNeural",
        "female_0":  "fr-FR-DeniseNeural",
        "female_1":  "fr-FR-VivienneMultilingualNeural",
        "female_2":  "fr-FR-EloiseNeural",
        "neutral_0": "fr-FR-DeniseNeural",
        "neutral_1": "fr-FR-HenriNeural",
    },
}

_DEFAULT_LOCALE = "en-US"
# Profile code (language_profiles.resolve_profile) -> EdgeTTS locale.
_PROFILE_LOCALE: dict[str, str] = {"en": "en-US", "fr": "fr-FR"}
# Normalise EdgeTTS MP3 output to a fixed rate so WAV segments are always
# assembly-compatible regardless of what Edge actually streams.
_OUTPUT_SAMPLE_RATE = 22050


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit signed PCM
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, settings: Settings, language: str | None = None) -> None:
        # `language` is Book.language (raw EPUB metadata, e.g. "en-US", "fr", None) --
        # resolved through the same profile logic as LLM segmentation so a book's
        # locale is consistent across the whole pipeline. Falls back to the global
        # EDGETTS_LOCALE when the book has no usable language (zero regression on
        # books analysed before this per-book resolution existed).
        if language:
            locale = _PROFILE_LOCALE[resolve_profile(language).code]
        else:
            locale = getattr(settings, "edgetts_locale", _DEFAULT_LOCALE) or _DEFAULT_LOCALE
        self._locale = locale
        self._voice_map: dict[str, str] = _VOICE_MAP.get(locale, _VOICE_MAP[_DEFAULT_LOCALE])

    def resolve_voice(self, voice_id: str) -> str:
        """Return the EdgeTTS neural voice name for a logical voice_id."""
        voice = self._voice_map.get(voice_id)
        if voice is None:
            raise TTSError(
                f"edgetts:{voice_id}",
                ValueError(f"Unknown voice_id {voice_id!r} for locale {self._locale!r}"),
            )
        return voice

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        # emotion and reference_audio_path accepted for interface parity but ignored (EdgeTTS has no emotion/clone control).
        edge_voice = self.resolve_voice(voice_id)  # raises TTSError if unknown

        mp3_chunks: list[bytes] = []
        try:
            communicate = edge_tts.Communicate(text, edge_voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])
        except Exception as exc:
            raise TTSError(f"edgetts:{voice_id}", exc)

        try:
            decoded = miniaudio.decode(
                data=b"".join(mp3_chunks),
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=_OUTPUT_SAMPLE_RATE,
            )
        except Exception as exc:
            raise TTSError(f"edgetts:{voice_id}:mp3_decode", exc)

        return _pcm_to_wav(decoded.samples.tobytes(), _OUTPUT_SAMPLE_RATE)
