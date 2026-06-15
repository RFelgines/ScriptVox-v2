from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.schemas.voice import VoiceResponse
from app.services.voice_assignment import list_catalogue_voices

router = APIRouter()


@router.get("", response_model=list[VoiceResponse])
def get_voices(settings: Settings = Depends(get_settings)) -> list[VoiceResponse]:
    # Only edgetts carries an intrinsic locale; piper/elevenlabs resolve voices
    # from on-disk models / remote UUIDs, so locale stays None there.
    locale = settings.edgetts_locale if settings.tts_provider == "edgetts" else None
    return [
        VoiceResponse(id=voice_id, gender=gender, locale=locale)
        for voice_id, gender in list_catalogue_voices()
    ]
