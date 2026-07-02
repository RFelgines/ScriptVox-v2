from typing import Literal

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    default_tts_provider: str
    # Préférence éditable en Paramètres -- PAS ENCORE utilisée pour piloter la
    # génération réelle (câblage différé, voir app_setting.py).
    preferred_tts_provider: str | None
    available_tts_providers: list[str]


class SettingsUpdate(BaseModel):
    preferred_tts_provider: str | None = None


class ProviderStatus(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str | None = None


class StatusResponse(BaseModel):
    llm: ProviderStatus
    tts: ProviderStatus
    cloned_voices_count: int
