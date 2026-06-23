from fastapi import APIRouter, Depends

from app.config import VALID_TTS_PROVIDERS, Settings, get_settings
from app.schemas.settings import SettingsResponse

router = APIRouter()


@router.get("", response_model=SettingsResponse)
def get_app_settings(settings: Settings = Depends(get_settings)) -> SettingsResponse:
    return SettingsResponse(
        default_tts_provider=settings.tts_provider,
        available_tts_providers=sorted(VALID_TTS_PROVIDERS),
    )
