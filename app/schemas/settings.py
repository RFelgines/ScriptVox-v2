from typing import Literal

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    default_tts_provider: str
    # Préférence éditable en Paramètres, appliquée par app.workers.tasks
    # ._effective_tts_provider entre l'override par livre et le défaut usine.
    preferred_tts_provider: str | None
    available_tts_providers: list[str]
    # Repli utilisé par app.workers.tasks._analyze_book quand dc:language est
    # absent/non reconnu à l'import EPUB -- n'affecte jamais un Book dont la
    # langue a déjà été détectée ou définie manuellement.
    preferred_language: str | None
    available_languages: list[str]


class SettingsUpdate(BaseModel):
    preferred_tts_provider: str | None = None
    preferred_language: str | None = None


class ProviderStatus(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str | None = None


class StatusResponse(BaseModel):
    llm: ProviderStatus
    tts: ProviderStatus
    cloned_voices_count: int
