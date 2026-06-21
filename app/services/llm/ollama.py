import logging

import httpx
import ollama as ollama_lib

from app.config import Settings
from app.core.exceptions import LLMParsingError
from app.services.llm.base import (
    BaseLLMProvider,
    LLMChapterResult,
    SYSTEM_PROMPT,
    _build_user_prompt,
    _parse_llm_json,
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
        raw = ""
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
            raw = response.message.content
            return _parse_llm_json(raw, spans)
        except LLMParsingError:
            raise
        except Exception as exc:
            raise LLMParsingError(raw, exc) from exc
