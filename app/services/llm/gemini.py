import asyncio
import logging

from google import genai
from google.genai import types as genai_types

from app.config import Settings
from app.core.exceptions import LLMRequestError
from app.services.llm.base import (
    ANALYSIS_JSON_SCHEMA,
    BaseLLMProvider,
    CharacterData,
    GEMINI_MAX_TOKENS,
    LLMChapterResult,
    MERGE_JSON_SCHEMA,
    MERGE_SYSTEM_PROMPT,
    MergeSuggestion,
    SYSTEM_PROMPT,
    _build_merge_prompt,
    _build_user_prompt,
    _parse_llm_json,
    _parse_merge_json,
    _pre_segment,
)
from app.services.llm.language_profiles import resolve_profile

logger = logging.getLogger(__name__)

# Attente progressive (secondes) sur un quota dépassé (HTTP 429) ou une indisponibilité
# temporaire (503) : le palier gratuit de l'API renvoie 429 dès que le débit est dépassé.
_RETRY_DELAYS = (5, 15, 45)


def _is_retryable(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 503):
        return True
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "UNAVAILABLE" in text


class GeminiProvider(BaseLLMProvider):
    """Gemini (cloud). `options` (réglages à chaud) : model."""

    chunk_tokens = GEMINI_MAX_TOKENS

    def __init__(self, settings: Settings, options: dict | None = None) -> None:
        options = options or {}
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = options.get("model") or settings.gemini_model
        self._temperature = settings.llm_temperature

    def _config(self, system: str, schema: dict) -> genai_types.GenerateContentConfig:
        return genai_types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=self._temperature,
        )

    async def _generate(self, contents: str, system: str, schema: dict):
        last: Exception | None = None
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                return await self._client.aio.models.generate_content(
                    model=self._model, contents=contents, config=self._config(system, schema),
                )
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < len(_RETRY_DELAYS) and _is_retryable(exc):
                    logger.warning("gemini: %s — nouvel essai dans %ss", exc, _RETRY_DELAYS[attempt])
                    await asyncio.sleep(_RETRY_DELAYS[attempt])
                    continue
                break
        raise LLMRequestError(last) from last

    async def analyze(
        self, text: str, known_characters: list[str] | None = None,
        language: str | None = None,
    ) -> LLMChapterResult:
        spans = _pre_segment(text, resolve_profile(language))
        response = await self._generate(
            _build_user_prompt(spans, known_characters), SYSTEM_PROMPT, ANALYSIS_JSON_SCHEMA,
        )
        return _parse_llm_json(response.text, spans)

    async def suggest_merges(
        self, characters: list[CharacterData]
    ) -> list[MergeSuggestion]:
        if len(characters) < 2:
            return []
        response = await self._generate(
            _build_merge_prompt(characters), MERGE_SYSTEM_PROMPT, MERGE_JSON_SCHEMA,
        )
        return _parse_merge_json(response.text, characters)


def list_gemini_models(api_key: str | None) -> list[str]:
    """Modèles Gemini capables de generateContent (suggestions pour Paramètres)."""
    client = genai.Client(api_key=api_key)
    names = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if "generateContent" in actions:
            names.append(str(m.name).removeprefix("models/"))
    return sorted(names)
