from app.config import Settings
from app.services import registry
from app.services.tts.base import BaseTTSProvider


def get_tts_provider(
    settings: Settings, override: str | None = None, language: str | None = None,
    options: dict | None = None,
) -> BaseTTSProvider:
    """Instancie le provider TTS. `override` = nom choisi (livre / Paramètres) ; `options` =
    réglages à chaud (model, base_url, locale…, voir AppSetting.tts_options). Les plugins
    (plugins/tts/) sont résolus par le registre. Un nom inconnu (ex. « elevenlabs » resté sur
    un livre avant sa suppression) lève une erreur explicite au lieu de retomber sur Piper."""
    provider = override or settings.tts_provider
    return registry.build_tts_provider(provider, settings, options, language)
