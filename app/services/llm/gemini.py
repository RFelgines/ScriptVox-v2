import logging

from google import genai
from google.genai import types as genai_types

from app.config import Settings
from app.core.exceptions import LLMRequestError
from app.services.llm.base import (
    BaseLLMProvider,
    CharacterData,
    LLMChapterResult,
    MERGE_SYSTEM_PROMPT,
    MergeSuggestion,
    SYSTEM_PROMPT,
    _build_merge_prompt,
    _build_user_prompt,
    _parse_llm_json,
    _parse_merge_json,
    _pre_segment,
)

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

    async def analyze(
        self, text: str, known_characters: list[str] | None = None
    ) -> LLMChapterResult:
        spans = _pre_segment(text)
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_build_user_prompt(spans, known_characters),
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_llm_json(response.text, spans)

    async def suggest_merges(
        self, characters: list[CharacterData]
    ) -> list[MergeSuggestion]:
        if len(characters) < 2:
            return []
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_build_merge_prompt(characters),
                config=genai_types.GenerateContentConfig(
                    system_instruction=MERGE_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_merge_json(response.text, characters)
