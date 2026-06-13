from app.config import Settings
from app.services.llm.base import BaseLLMProvider


def get_llm_provider(settings: Settings) -> BaseLLMProvider:
    if settings.llm_provider == "gemini":
        from app.services.llm.gemini import GeminiProvider
        return GeminiProvider(settings)
    from app.services.llm.ollama import OllamaProvider
    return OllamaProvider(settings)
