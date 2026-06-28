from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.config import VALID_TTS_PROVIDERS, Settings, get_settings
from app.core.db import get_session
from app.core.enums import VoiceKind
from app.models.entities import Voice
from app.schemas.settings import ProviderStatus, SettingsResponse, StatusResponse

router = APIRouter()


@router.get("", response_model=SettingsResponse)
def get_app_settings(settings: Settings = Depends(get_settings)) -> SettingsResponse:
    return SettingsResponse(
        default_tts_provider=settings.tts_provider,
        available_tts_providers=sorted(VALID_TTS_PROVIDERS),
    )


def _probe_llm(settings: Settings) -> ProviderStatus:
    if settings.llm_provider == "gemini":
        return ProviderStatus(
            name=f"Gemini ({settings.gemini_model})",
            status="ok",
            detail="Clé API configurée",
        )
    # ollama
    model = settings.ollama_model
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
        r.raise_for_status()
        tags = r.json()
        loaded = [m["name"] for m in tags.get("models", [])]
        if any(model in name for name in loaded):
            return ProviderStatus(name=f"Ollama — {model}", status="ok", detail="Modèle chargé")
        return ProviderStatus(
            name=f"Ollama — {model}",
            status="warning",
            detail=f"Ollama répond mais le modèle '{model}' n'apparaît pas dans /api/tags",
        )
    except Exception as exc:
        return ProviderStatus(
            name=f"Ollama — {model}",
            status="error",
            detail=f"Ollama injoignable : {exc}",
        )


def _probe_tts(settings: Settings) -> ProviderStatus:
    p = settings.tts_provider

    if p == "edgetts":
        locale = getattr(settings, "edgetts_locale", "fr-FR")
        return ProviderStatus(name=f"EdgeTTS ({locale})", status="ok", detail="Cloud, toujours disponible")

    if p == "elevenlabs":
        return ProviderStatus(name="ElevenLabs", status="ok", detail="Clé API configurée")

    if p == "piper":
        binary_ok = Path(settings.piper_binary_path).is_file()
        voices_ok = Path(settings.piper_voices_dir).is_dir()
        if binary_ok and voices_ok:
            n = len(list(Path(settings.piper_voices_dir).glob("*.onnx")))
            return ProviderStatus(
                name="Piper (local)",
                status="ok",
                detail=f"Binaire prêt · {n} modèle(s) .onnx trouvé(s)",
            )
        missing = []
        if not binary_ok:
            missing.append("binaire introuvable")
        if not voices_ok:
            missing.append("dossier voix introuvable")
        return ProviderStatus(name="Piper (local)", status="error", detail=", ".join(missing))

    if p == "qwen":
        model = getattr(settings, "qwen_model", "1.7b")
        device = getattr(settings, "qwen_device", "cuda:0")
        return ProviderStatus(
            name=f"Qwen3-TTS ({model})",
            status="ok",
            detail=f"Configuré — device {device} (chargement au premier usage)",
        )

    return ProviderStatus(name=p, status="warning", detail="Provider inconnu")


@router.get("/status", response_model=StatusResponse)
def get_app_status(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> StatusResponse:
    cloned_count = session.exec(
        select(func.count()).select_from(Voice).where(Voice.kind == VoiceKind.CLONED)
    ).one()
    return StatusResponse(
        llm=_probe_llm(settings),
        tts=_probe_tts(settings),
        cloned_voices_count=cloned_count,
    )
