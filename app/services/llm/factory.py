from app.config import Settings
from app.services import registry
from app.services.llm.base import BaseLLMProvider


def get_llm_provider(
    settings: Settings, override: str | None = None, options: dict | None = None,
) -> BaseLLMProvider:
    """Instancie le provider LLM. `override` = nom choisi à chaud (Paramètres) ; `options` =
    réglages à chaud du moteur (model, base_url…, voir AppSetting.llm_options) qui priment sur
    le .env. Les plugins (plugins/llm/) sont résolus par le registre."""
    provider = override or settings.llm_provider
    return registry.build_llm_provider(provider, settings, options)
