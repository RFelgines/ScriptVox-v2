import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.core.db import get_session
from app.core.enums import Gender, VoiceKind
from app.core.exceptions import TTSError
from app.models.entities import Voice
from app.schemas.voice import VoiceResponse, VoiceUpdate
from app.services.tts.base import BaseTTSProvider
from app.services.tts.factory import get_tts_provider

router = APIRouter()

DATA_DIR = Path("data")
_SAMPLE_TEXT = "Bonjour, ceci est un aperçu de cette voix."


def get_tts_provider_dep(settings: Settings = Depends(get_settings)) -> BaseTTSProvider:
    return get_tts_provider(settings)


def _name_to_slug(name: str) -> str:
    """Derive a stable, URL-safe voice_id from a human name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "voice"


def _voice_to_response(voice: Voice, locale: str | None) -> VoiceResponse:
    return VoiceResponse(
        id=voice.voice_id,
        name=voice.name,
        kind=voice.kind,
        gender=voice.gender,
        locale=locale,
        is_favorite=voice.is_favorite,
        has_reference_audio=voice.reference_audio_path is not None,
    )


@router.get("", response_model=list[VoiceResponse])
def get_voices(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> list[VoiceResponse]:
    locale = settings.edgetts_locale if settings.tts_provider == "edgetts" else None
    voices = session.exec(select(Voice).order_by(Voice.id)).all()
    return [_voice_to_response(v, locale) for v in voices]


@router.post("", response_model=VoiceResponse, status_code=201)
async def create_voice(
    file: UploadFile = File(..., description="Reference audio (MP3, WAV, FLAC, 3-15 s)"),
    name: str = Form(...),
    gender: Optional[Gender] = Form(None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> VoiceResponse:
    slug = _name_to_slug(name)
    existing = session.exec(select(Voice).where(Voice.voice_id == slug)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"A voice with id {slug!r} already exists.")

    ext = Path(file.filename or "ref.wav").suffix.lower() or ".wav"
    ref_dir = DATA_DIR / "voices" / slug
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_path = ref_dir / f"ref{ext}"
    try:
        ref_path.write_bytes(await file.read())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save reference audio: {exc}") from exc

    voice = Voice(
        voice_id=slug,
        name=name,
        kind=VoiceKind.CLONED,
        gender=gender,
        reference_audio_path=str(ref_path),
    )
    session.add(voice)
    session.commit()
    session.refresh(voice)

    locale = settings.edgetts_locale if settings.tts_provider == "edgetts" else None
    return _voice_to_response(voice, locale)


@router.patch("/{voice_id}", response_model=VoiceResponse)
def patch_voice(
    voice_id: str,
    body: VoiceUpdate,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> VoiceResponse:
    voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Unknown voice_id: {voice_id!r}")
    voice.is_favorite = body.is_favorite
    session.add(voice)
    session.commit()
    session.refresh(voice)
    locale = settings.edgetts_locale if settings.tts_provider == "edgetts" else None
    return _voice_to_response(voice, locale)


@router.delete("/{voice_id}", status_code=204)
def delete_voice(
    voice_id: str,
    session: Session = Depends(get_session),
) -> None:
    voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Unknown voice_id: {voice_id!r}")
    if voice.kind == VoiceKind.CATALOGUE:
        raise HTTPException(status_code=403, detail="Cannot delete a catalogue voice.")
    if voice.reference_audio_path:
        ref = Path(voice.reference_audio_path)
        if ref.exists():
            ref.unlink()
        try:
            ref.parent.rmdir()
        except OSError:
            pass
    session.delete(voice)
    session.commit()


@router.get("/{voice_id}/sample")
async def get_voice_sample(
    voice_id: str,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    provider: BaseTTSProvider = Depends(get_tts_provider_dep),
) -> FileResponse:
    voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Unknown voice_id: {voice_id!r}")

    cache_dir = DATA_DIR / "voice_samples"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{settings.tts_provider}_{voice_id}.wav"

    if not cache_path.exists():
        try:
            audio_bytes = await provider.synthesise(
                _SAMPLE_TEXT, voice_id,
                reference_audio_path=voice.reference_audio_path,
            )
        except TTSError as exc:
            raise HTTPException(status_code=502, detail=f"TTS sample failed: {exc}") from exc
        cache_path.write_bytes(audio_bytes)

    return FileResponse(str(cache_path), media_type="audio/wav", filename=cache_path.name)
