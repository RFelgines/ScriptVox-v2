"""Moteur TTS OmniVoice (k2-fsa) — client du serveur local scripts/omnivoice_server.py.

OmniVoice tourne dans son propre processus (.venv-omni) : il exige transformers>=5.3,
incompatible avec qwen-tts dans le même environnement. Voir le serveur pour l'installation.

LICENCE : poids du modèle sous CC-BY-NC — usage NON COMMERCIAL uniquement.

Ce qu'OmniVoice apporte à ScriptVox :
  - voix CONÇUES à partir d'une description (sexe, âge, hauteur, chuchotement, accent) :
    les 9 emplacements logiques (narrateur, male_N, female_N, neutral_N) sont décrits
    ci-dessous, et chaque personnage peut recevoir sa propre voix conçue
    (POST /characters/{id}/design-voice) ;
  - CLONAGE à partir d'un échantillon (voix de la bibliothèque) ;
  - une voix constante sur tout le livre : le serveur conçoit chaque description UNE fois
    puis la clone à chaque réplique ;
  - 600+ langues ; RTF 0,18 sur Radeon RX 9070 XT à 32 étapes (0,07 à 16).
Ce qu'il n'apporte pas : le contrôle de l'ÉMOTION par réplique (pas d'`instruct` libre
comme Qwen3-TTS CustomVoice). L'émotion ne module ici que le débit (voir _EMOTION_SPEED).

Configuration (.env ; base_url et num_step aussi modifiables à chaud dans Paramètres) :
  OMNIVOICE_URL        http://127.0.0.1:8770
  OMNIVOICE_NUM_STEP   étapes de diffusion (32 par défaut côté serveur ; 16 = 2,5x plus vite)
  OMNIVOICE_VOICE_MAP  JSON {"narrator": "male, middle-aged, low pitch", ...} (surcharge)
  OMNIVOICE_TIMEOUT    secondes par requête (600)
"""
import re
from pathlib import Path

import httpx

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.tts.base import BaseTTSProvider

# Emplacements logiques -> description OmniVoice (catégories : genre, âge, hauteur).
_VOICE_DESIGN: dict[str, str] = {
    "narrator":  "male, middle-aged, low pitch",
    "male_0":    "male, young adult, moderate pitch",
    "male_1":    "male, middle-aged, moderate pitch",
    "male_2":    "male, elderly, low pitch",
    "female_0":  "female, young adult, moderate pitch",
    "female_1":  "female, middle-aged, low pitch",
    "female_2":  "female, elderly, moderate pitch",
    "neutral_0": "female, teenager, high pitch",
    "neutral_1": "male, teenager, high pitch",
}

# L'émotion (texte libre fourni par le LLM) ne module que le débit : OmniVoice n'a pas de
# contrôle d'émotion. Réglage volontairement discret.
_EMOTION_SPEED: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(?i)col[èe]r|furieu|excit|press|panique|angry|furious|excited|urgent|hurried"), 1.08),
    (re.compile(r"(?i)trist|las|fatigu|mélancol|melancol|solennel|sad|tired|weary|solemn|slow"), 0.92),
]


def _dict_setting(settings, name: str) -> dict:
    value = getattr(settings, name, None)
    return value if isinstance(value, dict) else {}


def speed_for(emotion: str | None) -> float | None:
    if not emotion:
        return None
    for pattern, speed in _EMOTION_SPEED:
        if pattern.search(emotion):
            return speed
    return None


def reference_text(path: str) -> str | None:
    """Transcription de l'échantillon (fichier .txt à côté, même convention que Qwen)."""
    sidecar = Path(path).with_suffix(".txt")
    try:
        return sidecar.read_text(encoding="utf-8").strip() or None if sidecar.is_file() else None
    except OSError:
        return None


class OmniVoiceTTSProvider(BaseTTSProvider):
    supports_concurrency = 1   # un seul GPU : le serveur sérialise de toute façon
    supports_cloning = True
    max_chars = 600

    def __init__(self, settings: Settings, options: dict | None = None,
                 language: str | None = None) -> None:
        options = options or {}
        self._base_url = str(options.get("base_url") or settings.omnivoice_url).rstrip("/")
        self._num_step = options.get("num_step") or settings.omnivoice_num_step
        self._timeout = settings.omnivoice_timeout
        self._voice_map = dict(_VOICE_DESIGN)
        self._voice_map.update(_dict_setting(settings, "omnivoice_voice_map"))
        self._language = (language or "").strip().lower()[:2] or None

    def resolve_voice(self, voice_id: str) -> str:
        instruct = self._voice_map.get(voice_id)
        if instruct is None:
            raise TTSError(f"omnivoice:{voice_id}", ValueError(f"Unknown voice_id {voice_id!r}"))
        return instruct

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        body: dict = {"text": text, "language": self._language}
        if self._num_step:
            body["num_step"] = int(self._num_step)
        speed = speed_for(emotion)
        if speed:
            body["speed"] = speed
        if reference_audio_path:
            body["ref_audio_path"] = str(reference_audio_path)
            ref = reference_text(reference_audio_path)
            if ref:
                body["ref_text"] = ref
        else:
            body["instruct"] = self.resolve_voice(voice_id)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(f"{self._base_url}/synthesize", json=body)
        except httpx.HTTPError as exc:
            raise TTSError(
                f"omnivoice:{voice_id}",
                RuntimeError(f"serveur OmniVoice injoignable ({self._base_url}) — lancer "
                             f"scripts/omnivoice_server.py : {exc}"),
            ) from exc
        if r.status_code != 200:
            raise TTSError(f"omnivoice:{voice_id}", RuntimeError(f"HTTP {r.status_code} : {r.text[:300]}"))
        return r.content


async def design_voice(settings: Settings, instruct: str, language: str | None,
                       out_path: str | Path, options: dict | None = None) -> str:
    """Fait concevoir par le serveur l'échantillon de référence d'une voix (écrit, avec sa
    transcription .txt, à `out_path`). Retourne la transcription."""
    base = str((options or {}).get("base_url") or settings.omnivoice_url).rstrip("/")
    async with httpx.AsyncClient(timeout=settings.omnivoice_timeout) as client:
        r = await client.post(f"{base}/design", json={
            "instruct": instruct, "language": (language or "")[:2] or None, "out_path": str(out_path),
        })
    if r.status_code != 200:
        raise TTSError("omnivoice:design", RuntimeError(f"HTTP {r.status_code} : {r.text[:300]}"))
    return r.json()["reference_text"]


# ── Voix conçue d'un personnage ───────────────────────────────────────────────
_AGE = {"CHILD": "child", "YOUNG_ADULT": "young adult", "ADULT": "middle-aged", "ELDER": "elderly"}
_LOW = re.compile(r"(?i)grave|profond|sourd|rauque|basse|deep|low|husky|gravel|bass|baritone")
_HIGH = re.compile(r"(?i)aigu|aigü|flût|perçant|claire?\b|haute|high|shrill|squeak|piping|bright")
_WHISPER = re.compile(r"(?i)chuchot|murmur|souffl|whisper|breathy")


def instruct_for_character(gender: str | None, age_category: str | None,
                           voice_quality: str | None = None, voice_tone: str | None = None,
                           description: str | None = None) -> str:
    """Description OmniVoice (catégories genre, âge, hauteur, style) déduite de la fiche du
    personnage établie par le LLM. Une seule valeur par catégorie ; les attributs que
    l'analyse n'a pas déterminés sont omis plutôt qu'inventés."""
    g = str(getattr(gender, "value", gender) or "").upper()
    a = str(getattr(age_category, "value", age_category) or "").upper()
    parts: list[str] = []
    if g in ("MALE", "FEMALE"):
        parts.append(g.lower())
    if a in _AGE:
        parts.append(_AGE[a])
    hints = " ".join(x for x in (voice_quality, voice_tone, description) if x)
    if _WHISPER.search(hints):
        parts.append("whisper")
    elif _LOW.search(hints):
        parts.append("low pitch")
    elif _HIGH.search(hints):
        parts.append("high pitch")
    else:
        parts.append("moderate pitch")
    return ", ".join(parts)
