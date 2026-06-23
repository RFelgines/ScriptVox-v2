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
    _compute_read_timeout,
    _parse_llm_json,
    _parse_merge_json,
    _pre_segment,
)

logger = logging.getLogger(__name__)

# Qwen3 reasoning models emit a hidden <think> block by default, costing time and context
# budget for no benefit on this structured-extraction task. /no_think is Qwen3's documented
# soft-switch, read from the latest user turn (see ARCHITECTURE.md §2.5).
_NO_THINK_SUFFIX = "\n\n/no_think"


class OllamaProvider(BaseLLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._connect_timeout = settings.ollama_connect_timeout
        self._read_timeout_floor = settings.ollama_read_timeout
        self._timeout_per_1k_tokens = settings.ollama_timeout_per_1k_tokens
        self._client = ollama_lib.AsyncClient(
            host=settings.ollama_base_url,
            timeout=httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout_floor,
                write=None,
                pool=None,
            ),
        )
        self._model = settings.ollama_model
        self._num_ctx = settings.ollama_context_tokens

    def _set_dynamic_read_timeout(self, prompt: str) -> None:
        read_timeout = _compute_read_timeout(
            prompt, self._read_timeout_floor, self._timeout_per_1k_tokens
        )
        self._client._client.timeout = httpx.Timeout(
            connect=self._connect_timeout, read=read_timeout, write=None, pool=None,
        )

    async def analyze(
        self, text: str, known_characters: list[str] | None = None
    ) -> LLMChapterResult:
        spans = _pre_segment(text)
        prompt = _build_user_prompt(spans, known_characters) + _NO_THINK_SUFFIX
        self._set_dynamic_read_timeout(prompt)
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
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
        prompt = _build_merge_prompt(characters) + _NO_THINK_SUFFIX
        self._set_dynamic_read_timeout(prompt)
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format="json",
                options={"num_ctx": self._num_ctx},
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_merge_json(response.message.content, characters)
