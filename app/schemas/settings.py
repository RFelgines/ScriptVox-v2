from typing import Literal

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    default_tts_provider: str
    available_tts_providers: list[str]


class ProviderStatus(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str | None = None


class StatusResponse(BaseModel):
    llm: ProviderStatus
    tts: ProviderStatus
    cloned_voices_count: int
