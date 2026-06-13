import logging

from google import genai
from google.genai import types as genai_types

from app.config import Settings
from app.core.exceptions import LLMParsingError
from app.services.llm.base import (
    BaseLLMProvider,
    LLMChapterResult,
    SYSTEM_PROMPT,
    _parse_llm_json,
)

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

    async def analyze(self, text: str) -> LLMChapterResult:
        raw = ""
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=text,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text
            return _parse_llm_json(raw)
        except LLMParsingError:
            raise
        except Exception as exc:
            raise LLMParsingError(raw, exc) from exc
