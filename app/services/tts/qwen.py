import asyncio
from pathlib import Path

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.audio.format import OUTPUT_SAMPLE_RATE, float_to_pcm16, pcm16_to_wav, resample_pcm16
from app.services.llm.language_profiles import resolve_profile
from app.services.tts.base import BaseTTSProvider

# Logical voice_id -> Qwen3-TTS speaker preset (CustomVoice variants).
# IDs mirror VOICE_CATALOGUE (voice_assignment.py): narrator + male_N / female_N / neutral_N.
# Qwen3-TTS ships exactly 9 presets (Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden,
# Ono_Anna, Sohee) -- one per logical slot. Mapping confirmed by ear (B3 listening pass,
# 2026-06-27). Surchargeable via QWEN_VOICE_MAP (JSON) pour un checkpoint aux presets différents.
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

# Base checkpoint: voice cloning via generate_voice_clone.
# Must NOT cohabitate with CustomVoice on a 10-16 Go GPU — sequential swap strategy.
_MODEL_IDS_BASE: dict[str, str] = {
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}

# Profile code (language_profiles.resolve_profile) -> Qwen3-TTS language string.
# Qwen3-TTS annonce 10 langues (dont l'espagnol) : ajouter une entrée ici suffit
# côté moteur, le travail réel étant le LanguageProfile correspondant.
_PROFILE_LANGUAGE: dict[str, str] = {
    "en": "English", "fr": "French", "es": "Spanish", "de": "German", "it": "Italian",
}

_MODEL_SAMPLE_RATE = 24000   # what Qwen3-TTS always returns (verified by tests/spike_qwen_tts.py)
_OUTPUT_SAMPLE_RATE = OUTPUT_SAMPLE_RATE  # 24 kHz : plus aucun rééchantillonnage nécessaire


def _import_qwen_deps():
    # Isolated in its own function so tests can patch it to simulate a missing install
    # without needing torch/qwen-tts to actually be absent.
    import torch
    from qwen_tts import Qwen3TTSModel
    return torch, Qwen3TTSModel


def _float_to_pcm16(samples) -> bytes:
    """Float32 audio in [-1, 1] -> 16-bit signed PCM (vectorisé numpy)."""
    return float_to_pcm16(samples)


def _resample_to_output(pcm16: bytes, source_rate: int) -> bytes:
    if source_rate == _OUTPUT_SAMPLE_RATE:
        return pcm16
    return resample_pcm16(pcm16, source_rate, _OUTPUT_SAMPLE_RATE)


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    return pcm16_to_wav(pcm, sample_rate)


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


def _is_custom_model_id(value: str) -> bool:
    """« 1.7b » / « 0.6b » = raccourcis ; tout autre texte est pris tel quel comme identifiant
    Hugging Face (« org/nom ») ou chemin local d'un checkpoint compatible."""
    return value.lower() not in _MODEL_IDS


class QwenTTSProvider(BaseTTSProvider):
    """Qwen3-TTS local (GPU). Modèle gardé chargé d'un chapitre à l'autre (BE-1).

    `options` (réglages à chaud) : `model` = « 1.7b » | « 0.6b » | identifiant Hugging Face /
    chemin local d'un checkpoint CustomVoice compatible ; `base_model` = idem pour le checkpoint
    de clonage (sinon déduit : même taille si raccourci, sinon QWEN_BASE_MODEL).
    """

    keep_loaded = True
    max_chars = 400  # au-delà, les TTS neuronaux dérivent ou tronquent (TTS-5)

    def __init__(self, settings: Settings, language: str | None = None,
                 options: dict | None = None) -> None:
        options = options or {}
        size = str(options.get("model") or getattr(settings, "qwen_model", "1.7b"))
        if _is_custom_model_id(size):
            self._model_id = size
            base = options.get("base_model") or getattr(settings, "qwen_base_model", None)
            self._base_model_id = base if isinstance(base, str) and base else _MODEL_IDS_BASE["1.7b"]
        else:
            self._model_id = _MODEL_IDS[size.lower()]
            self._base_model_id = options.get("base_model") or _MODEL_IDS_BASE[size.lower()]
        # `language` is Book.language (raw EPUB metadata) -- resolved through the same
        # profile logic as LLM segmentation / EdgeTTS so a book's locale is consistent
        # across the whole pipeline. Falls back to the global QWEN_LANGUAGE when the
        # book has no usable language (zero regression on books analysed before this
        # per-book resolution existed).
        if language:
            self._language = _PROFILE_LANGUAGE[resolve_profile(language).code]
        else:
            self._language = getattr(settings, "qwen_language", "French")
        self._device = getattr(settings, "qwen_device", "cuda:0")
        self._attn = getattr(settings, "qwen_attn", "sdpa")
        override = getattr(settings, "qwen_voice_map", None)
        self._voice_map = {**_VOICE_MAP, **(override if isinstance(override, dict) else {})}
        self._model = None       # CustomVoice — lazy-loaded on first preset call
        self._base_model = None  # Base — lazy-loaded on first clone call
        self._ref_cache: dict[str, tuple] = {}
        self._prompt_cache: dict[str, object] = {}

    def resolve_voice(self, voice_id: str) -> str:
        """Return the Qwen3-TTS speaker preset for a logical voice_id."""
        speaker = self._voice_map.get(voice_id)
        if speaker is None:
            raise TTSError(
                f"qwen:{voice_id}",
                ValueError(f"Unknown voice_id {voice_id!r} for Qwen3-TTS"),
            )
        return speaker

    def unload(self) -> None:
        """Libère la VRAM (modèles CustomVoice et Base)."""
        if self._model is None and self._base_model is None:
            return
        import gc
        self._model = None
        self._base_model = None
        self._prompt_cache.clear()  # les prompts de clonage vivent sur le GPU
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

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

    def _reference(self, path: str):
        """Audio de référence décodé UNE fois par voix (avant : relu à chaque réplique)."""
        if path not in self._ref_cache:
            self._ref_cache[path] = _load_ref_audio(path)
        return self._ref_cache[path]

    @staticmethod
    def _reference_text(path: str) -> str | None:
        """Transcription de l'audio de référence : fichier `ref.txt` posé à côté de `ref.<ext>`
        à la création de la voix. Avec elle, le clonage est « complet » (timbre + prosodie) ;
        sans, retour au mode x-vector seul (timbre uniquement)."""
        sidecar = Path(path).with_suffix(".txt")
        try:
            text = sidecar.read_text(encoding="utf-8").strip() if sidecar.is_file() else ""
        except OSError:
            text = ""
        return text or None

    def _clone_kwargs(self, model, path: str) -> dict:
        """Arguments de clonage. Le prompt de clonage (encodage de la référence) est calculé UNE
        fois par voix puis réutilisé pour toutes ses répliques quand l'API du modèle le permet
        (create_voice_clone_prompt) ; sinon la référence est passée telle quelle à chaque appel."""
        samples_f32, ref_sr = self._reference(path)
        ref_text = self._reference_text(path)
        if not ref_text:
            return {"ref_audio": (samples_f32, ref_sr), "x_vector_only_mode": True}
        prompt = self._prompt_cache.get(path)
        if prompt is None and hasattr(model, "create_voice_clone_prompt"):
            try:
                prompt = model.create_voice_clone_prompt(
                    ref_audio=(samples_f32, ref_sr), ref_text=ref_text, x_vector_only_mode=False,
                )
                self._prompt_cache[path] = prompt
            except Exception:  # noqa: BLE001 — API différente selon la version de qwen-tts
                prompt = None
        if prompt is not None:
            return {"voice_clone_prompt": prompt}
        return {"ref_audio": (samples_f32, ref_sr), "ref_text": ref_text, "x_vector_only_mode": False}

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        if reference_audio_path is not None:
            # Clone mode — Base checkpoint + generate_voice_clone
            def _run_clone() -> bytes:
                model = self._ensure_base_model()
                wavs, sample_rate = model.generate_voice_clone(
                    text=text,
                    language=self._language,
                    **self._clone_kwargs(model, reference_audio_path),
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
