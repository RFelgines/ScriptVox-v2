from app.config import Settings, VALID_LLM_PROVIDERS
from app.services.llm.base import BaseLLMProvider


def get_llm_provider(settings: Settings, override: str | None = None) -> BaseLLMProvider:
    provider = override or settings.llm_provider
    if provider == "gemini":
        from app.services.llm.gemini import GeminiProvider
        return GeminiProvider(settings)
    if provider == "ollama":
        from app.services.llm.ollama import OllamaProvider
        return OllamaProvider(settings)
    raise ValueError(
        f"Unknown llm_provider {provider!r}. Accepted values: {sorted(VALID_LLM_PROVIDERS)}"
    )
