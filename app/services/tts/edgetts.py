import io
import wave

import edge_tts
import miniaudio

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.audio.format import OUTPUT_SAMPLE_RATE
from app.services.llm.language_profiles import resolve_profile
from app.services.tts.base import BaseTTSProvider

# Logical voice_id -> EdgeTTS neural voice name, keyed by BCP-47 locale.
# IDs mirror VOICE_CATALOGUE (voice_assignment.py): narrator + male_N / female_N / neutral_N.
# Liste des voix vérifiée en direct (edge_tts.list_voices(), 2026-09-25). fr-FR n'a que 2 voix
# masculines et 3 féminines : les emplacements supplémentaires empruntent les voix francophones
# fr-CA / fr-BE / fr-CH pour qu'AUCUN personnage ne parle avec la voix du narrateur (avant :
# narrator == male_1 == male_2 == neutral_1 == Henri).
# Toute entrée est surchargeable via EDGETTS_VOICE_MAP (JSON) sans toucher au code :
#   {"male_1": "fr-CA-JeanNeural", "narrator": {"voice": "fr-FR-HenriNeural", "rate": "-5%"}}
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
        "male_1":    "fr-CA-AntoineNeural",
        "male_2":    "fr-BE-GerardNeural",
        "female_0":  "fr-FR-DeniseNeural",
        "female_1":  "fr-FR-VivienneMultilingualNeural",
        "female_2":  "fr-FR-EloiseNeural",
        "neutral_0": "fr-CH-ArianeNeural",
        "neutral_1": "fr-CA-ThierryNeural",
    },
    # es-ES ne compte que 3 voix (1 masculine, 2 féminines) : comme pour fr-FR, les
    # emplacements restants empruntent aux autres locales hispanophones pour qu'aucun
    # personnage ne parle avec la voix du narrateur. Noms vérifiés en direct via
    # edge_tts.list_voices() le 2026-09-26.
    "es-ES": {
        "narrator":  "es-ES-AlvaroNeural",
        "male_0":    "es-MX-JorgeNeural",
        "male_1":    "es-AR-TomasNeural",
        "male_2":    "es-CO-GonzaloNeural",
        "female_0":  "es-ES-ElviraNeural",
        "female_1":  "es-ES-XimenaNeural",
        "female_2":  "es-MX-DaliaNeural",
        "neutral_0": "es-CL-CatalinaNeural",
        "neutral_1": "es-PE-AlexNeural",
    },
}

_DEFAULT_LOCALE = "en-US"
# Profile code (language_profiles.resolve_profile) -> EdgeTTS locale.
_PROFILE_LOCALE: dict[str, str] = {"en": "en-US", "fr": "fr-FR", "es": "es-ES"}
# Fréquence de sortie commune à tout le pipeline (voir app/services/audio/format.py).
_OUTPUT_SAMPLE_RATE = OUTPUT_SAMPLE_RATE


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit signed PCM
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _dict_setting(settings, name: str) -> dict:
    value = getattr(settings, name, None)
    return value if isinstance(value, dict) else {}


class EdgeTTSProvider(BaseTTSProvider):
    """EdgeTTS (cloud). Appels réseau indépendants -> plusieurs synthèses en parallèle."""

    supports_concurrency = 6
    max_chars = 2000

    def __init__(self, settings: Settings, language: str | None = None,
                 options: dict | None = None) -> None:
        # `language` is Book.language (raw EPUB metadata, e.g. "en-US", "fr", None) --
        # resolved through the same profile logic as LLM segmentation so a book's
        # locale is consistent across the whole pipeline. Falls back to the global
        # EDGETTS_LOCALE (ou au réglage à chaud `locale`) when the book has no usable language.
        options = options or {}
        if language:
            locale = _PROFILE_LOCALE[resolve_profile(language).code]
        else:
            locale = (
                options.get("locale")
                or getattr(settings, "edgetts_locale", _DEFAULT_LOCALE)
                or _DEFAULT_LOCALE
            )
        self._locale = locale
        self._voice_map: dict = dict(_VOICE_MAP.get(locale, _VOICE_MAP[_DEFAULT_LOCALE]))
        self._voice_map.update(_dict_setting(settings, "edgetts_voice_map"))

    def _entry(self, voice_id: str) -> tuple[str, str | None, str | None]:
        entry = self._voice_map.get(voice_id)
        if entry is None:
            raise TTSError(
                f"edgetts:{voice_id}",
                ValueError(f"Unknown voice_id {voice_id!r} for locale {self._locale!r}"),
            )
        if isinstance(entry, dict):
            return entry["voice"], entry.get("pitch"), entry.get("rate")
        return str(entry), None, None

    def resolve_voice(self, voice_id: str) -> str:
        """Return the EdgeTTS neural voice name for a logical voice_id."""
        return self._entry(voice_id)[0]

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        # emotion and reference_audio_path accepted for interface parity but ignored (EdgeTTS has no emotion/clone control).
        edge_voice, pitch, rate = self._entry(voice_id)  # raises TTSError if unknown

        mp3_chunks: list[bytes] = []
        try:
            kwargs = {}
            if pitch:
                kwargs["pitch"] = pitch
            if rate:
                kwargs["rate"] = rate
            communicate = edge_tts.Communicate(text, edge_voice, **kwargs)
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
