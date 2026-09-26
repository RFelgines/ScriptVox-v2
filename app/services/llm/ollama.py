import logging

import httpx
import ollama as ollama_lib

from app.config import Settings
from app.core.exceptions import LLMRequestError
from app.services.llm.base import (
    ANALYSIS_JSON_SCHEMA,
    BaseLLMProvider,
    CharacterData,
    LLMChapterResult,
    MERGE_JSON_SCHEMA,
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
from app.services.llm.language_profiles import resolve_profile

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama local. `options` (réglages à chaud) : model, base_url."""

    def __init__(self, settings: Settings, options: dict | None = None) -> None:
        options = options or {}
        self._connect_timeout = settings.ollama_connect_timeout
        self._read_timeout_floor = settings.ollama_read_timeout
        self._timeout_per_1k_tokens = settings.ollama_timeout_per_1k_tokens
        self._base_url = options.get("base_url") or settings.ollama_base_url
        self._client = ollama_lib.AsyncClient(
            host=self._base_url,
            timeout=httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout_floor,
                write=None,
                pool=None,
            ),
        )
        self._model = options.get("model") or settings.ollama_model
        self._num_ctx = settings.ollama_context_tokens
        self._temperature = settings.llm_temperature
        self.chunk_tokens = settings.ollama_chunk_tokens

    def _set_dynamic_read_timeout(self, prompt: str) -> None:
        read_timeout = _compute_read_timeout(
            prompt, self._read_timeout_floor, self._timeout_per_1k_tokens
        )
        self._client._client.timeout = httpx.Timeout(
            connect=self._connect_timeout, read=read_timeout, write=None, pool=None,
        )

    def _chat_options(self) -> dict:
        return {"num_ctx": self._num_ctx, "temperature": self._temperature}

    async def analyze(
        self, text: str, known_characters: list[str] | None = None,
        language: str | None = None,
    ) -> LLMChapterResult:
        spans = _pre_segment(text, resolve_profile(language))
        prompt = _build_user_prompt(spans, known_characters)
        self._set_dynamic_read_timeout(prompt)
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format=ANALYSIS_JSON_SCHEMA,
                think=False,
                options=self._chat_options(),
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_llm_json(response.message.content, spans)

    async def suggest_merges(
        self, characters: list[CharacterData]
    ) -> list[MergeSuggestion]:
        if len(characters) < 2:
            return []
        prompt = _build_merge_prompt(characters)
        self._set_dynamic_read_timeout(prompt)
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format=MERGE_JSON_SCHEMA,
                think=False,
                options=self._chat_options(),
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_merge_json(response.message.content, characters)

    def unload(self) -> None:
        """Décharge le modèle de la VRAM (keep_alive=0). Synchrone : appelé depuis le worker,
        hors boucle asyncio ; best-effort, jamais d'exception."""
        try:
            httpx.post(
                f"{self._base_url.rstrip('/')}/api/generate",
                json={"model": self._model, "prompt": "", "keep_alive": 0},
                timeout=15.0,
            )
        except Exception:  # noqa: BLE001
            logger.warning("ollama unload failed for %s", self._model, exc_info=True)


def list_ollama_models(base_url: str, timeout: float = 3.0) -> list[str]:
    """Noms des modèles installés (GET /api/tags). Lève une exception si injoignable."""
    r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
    r.raise_for_status()
    return sorted(m["name"] for m in r.json().get("models", []))
