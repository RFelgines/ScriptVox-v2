from pydantic import BaseModel


class SettingsResponse(BaseModel):
    default_tts_provider: str
    available_tts_providers: list[str]
