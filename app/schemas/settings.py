from typing import Literal

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    default_tts_provider: str
    # Préférence éditable en Paramètres, appliquée par app.workers.tasks
    # ._effective_tts_provider entre l'override par livre et le défaut usine.
    preferred_tts_provider: str | None
    # Providers officiels + plugins (plugins/tts/) — voir app.services.registry.
    available_tts_providers: list[str]
    # Repli utilisé par app.workers.tasks._analyze_book quand dc:language est
    # absent/non reconnu à l'import EPUB -- n'affecte jamais un Book dont la
    # langue a déjà été détectée ou définie manuellement.
    preferred_language: str | None
    available_languages: list[str]
    # Préférence LLM éditable en Paramètres, résolue par _effective_llm_provider
    # à chaque run d'analyse (AppSetting > .env). None = défaut usine.
    default_llm_provider: str
    preferred_llm_provider: str | None
    available_llm_providers: list[str]
    # Réglages à chaud du moteur (model, base_url…) qui priment sur le .env : c'est ce qui
    # permet de changer de modèle depuis l'interface, y compris un modèle absent de toute liste.
    llm_options: dict[str, str] = Field(default_factory=dict)
    tts_options: dict[str, str] = Field(default_factory=dict)
    # Modèle effectivement utilisé (options > .env), pour l'affichage.
    effective_llm_model: str | None = None
    effective_tts_model: str | None = None
    llm_provider_descriptions: dict[str, str] = Field(default_factory=dict)
    tts_provider_descriptions: dict[str, str] = Field(default_factory=dict)
    # Plugins qui n'ont pas pu être chargés (fichier, erreur).
    plugin_errors: list[dict[str, str]] = Field(default_factory=list)


class SettingsUpdate(BaseModel):
    preferred_tts_provider: str | None = None
    preferred_language: str | None = None
    preferred_llm_provider: str | None = None
    # Remplace l'objet entier quand il est fourni ({} = effacer). Clés autorisées :
    # model, base_url, base_model, locale.
    llm_options: dict[str, str] | None = None
    tts_options: dict[str, str] | None = None


class ProviderStatus(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str | None = None


class StatusResponse(BaseModel):
    llm: ProviderStatus
    tts: ProviderStatus
    cloned_voices_count: int


class ModelListResponse(BaseModel):
    """Modèles proposés en suggestion. La liste n'est jamais limitative : n'importe quel nom
    saisi à la main est accepté (le moteur dira s'il l'ignore)."""
    provider: str
    models: list[str]
    error: str | None = None
