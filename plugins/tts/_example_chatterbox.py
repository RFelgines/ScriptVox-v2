"""ESQUISSE NON TESTÉE d'un plugin Chatterbox Multilingual (Resemble AI, licence MIT).

⚠️  Écrite d'après la documentation publique du projet, JAMAIS exécutée ici : l'API de la
bibliothèque peut différer selon la version installée. À utiliser comme point de départ.

Prérequis (dans l'environnement Python de ScriptVox) : `pip install chatterbox-tts` et un PyTorch
adapté à votre GPU (voir requirements-qwen.txt pour NVIDIA / AMD ROCm).
Copier en `chatterbox.py` (sans le `_`) pour l'activer, puis choisir « chatterbox » dans Paramètres.

Intérêt pour ScriptVox : un curseur d'intensité émotionnelle (`exaggeration`, 0-1) et le clonage de
voix à partir d'un court échantillon. L'« émotion » texte de chaque réplique est convertie ici en
une intensité simple ; à affiner à l'oreille (voir scripts/bench_tts.py).
"""
import asyncio

from app.core.exceptions import TTSError
from app.services.audio.format import float_to_pcm16, pcm16_to_wav
from app.services.tts.base import BaseTTSProvider

PROVIDER_NAME = "chatterbox"
DESCRIPTION = "Chatterbox Multilingual (esquisse non testée)"

_LANG = {"fr": "fr", "en": "en"}
_CALM = ("calm", "calme", "neutral", "neutre", "soft", "doux")


def _exaggeration(emotion: str | None) -> float:
    if not emotion:
        return 0.5
    return 0.3 if any(w in emotion.lower() for w in _CALM) else 0.75


class ChatterboxProvider(BaseTTSProvider):
    keep_loaded = True   # le modèle reste en VRAM d'un chapitre à l'autre
    max_chars = 300

    def __init__(self, device: str, language: str | None):
        self._device = device
        self._lang = _LANG.get((language or "fr")[:2].lower(), "fr")
        self._model = None

    def _load(self):
        if self._model is None:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # import paresseux (lourd)
            self._model = ChatterboxMultilingualTTS.from_pretrained(device=self._device)
        return self._model

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        def _run() -> bytes:
            model = self._load()
            wav = model.generate(
                text,
                language_id=self._lang,
                audio_prompt_path=reference_audio_path,  # None = voix par défaut du modèle
                exaggeration=_exaggeration(emotion),
            )
            samples = wav.squeeze().detach().cpu().numpy()
            return pcm16_to_wav(float_to_pcm16(samples), int(model.sr))

        try:
            return await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as exc:
            raise TTSError(f"chatterbox:{voice_id}", exc)

    def unload(self) -> None:
        self._model = None
        try:
            import gc
            import torch
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass


def create(settings, options, language=None):
    return ChatterboxProvider(getattr(settings, "qwen_device", "cuda:0"), language)
