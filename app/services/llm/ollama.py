import logging

import httpx
import ollama as ollama_lib

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


class OllamaProvider(BaseLLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = ollama_lib.AsyncClient(
            host=settings.ollama_base_url,
            timeout=httpx.Timeout(
                connect=settings.ollama_connect_timeout,
                read=settings.ollama_read_timeout,
                write=None,
                pool=None,
            ),
        )
        self._model = settings.ollama_model
        self._num_ctx = settings.ollama_context_tokens

    async def analyze(
        self, text: str, known_characters: list[str] | None = None
    ) -> LLMChapterResult:
        spans = _pre_segment(text)
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(spans, known_characters)},
                ],
                format="json",
                options={"num_ctx": self._num_ctx},
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_llm_json(response.message.content, spans)

    async def suggest_merges(
        self, characters: list[CharacterData]
    ) -> list[MergeSuggestion]:
        if len(characters) < 2:
            return []
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_merge_prompt(characters)},
                ],
                format="json",
                options={"num_ctx": self._num_ctx},
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_merge_json(response.message.content, characters)
