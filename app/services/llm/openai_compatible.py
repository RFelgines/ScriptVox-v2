"""Provider LLM pour tout serveur exposant l'API OpenAI Chat Completions.

Couvre LM Studio, llama.cpp (`llama-server`), vLLM, LocalAI, Jan, OpenRouter, l'API OpenAI
elle-même, etc. — donc n'importe quel modèle (Qwen 3.8, Llama, Mistral…) sans code dédié.

Sortie contrainte : `response_format=json_schema` (le plus fiable) ; si le serveur le refuse
(HTTP 400/422), repli automatique sur `json_object`, puis sur du texte libre parsé tel quel.
"""
import logging

import httpx

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
    _parse_llm_json,
    _parse_merge_json,
    _pre_segment,
)
from app.services.llm.language_profiles import resolve_profile

logger = logging.getLogger(__name__)


def _extract_json(content: str) -> str:
    """Certains serveurs entourent le JSON de ```json … ``` ou d'un préambule : on isole
    l'objet le plus externe ; sinon on renvoie le texte tel quel (le parseur signalera)."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:].strip() if text[:4].lower() == "json" else text
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class OpenAICompatibleProvider(BaseLLMProvider):
    """`options` (réglages à chaud) : model, base_url. Clé API : OPENAI_API_KEY (.env)."""

    def __init__(self, settings: Settings, options: dict | None = None) -> None:
        options = options or {}
        self._base_url = (options.get("base_url") or settings.openai_base_url).rstrip("/")
        self._model = options.get("model") or settings.openai_model
        if not self._model:
            raise LLMRequestError(ValueError(
                "Aucun modèle défini : renseigner OPENAI_MODEL (.env) ou le modèle dans Paramètres."
            ))
        self._api_key = settings.openai_api_key
        self._timeout = settings.openai_timeout
        self._temperature = settings.llm_temperature
        self.chunk_tokens = settings.openai_chunk_tokens
        # Mémorise le meilleur mode accepté par CE serveur (évite de re-tester à chaque appel).
        self._mode = "json_schema"

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _payload(self, system: str, user: str, schema: dict, schema_name: str, mode: str) -> dict:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature,
            "stream": False,
        }
        if mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": False, "schema": schema},
            }
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _chat(self, system: str, user: str, schema: dict, schema_name: str) -> str:
        modes = ["json_schema", "json_object", "text"]
        modes = modes[modes.index(self._mode):]
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for mode in modes:
                try:
                    r = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=self._headers(),
                        json=self._payload(system, user, schema, schema_name, mode),
                    )
                except Exception as exc:  # noqa: BLE001
                    raise LLMRequestError(exc) from exc
                if r.status_code in (400, 422) and mode != "text":
                    last_error = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                    logger.info("openai_compatible: mode %s refusé, repli", mode)
                    continue
                try:
                    r.raise_for_status()
                    content = r.json()["choices"][0]["message"]["content"]
                except Exception as exc:  # noqa: BLE001
                    raise LLMRequestError(exc) from exc
                self._mode = mode
                return _extract_json(content)
        raise LLMRequestError(last_error or RuntimeError("réponse vide"))

    async def analyze(
        self, text: str, known_characters: list[str] | None = None,
        language: str | None = None,
    ) -> LLMChapterResult:
        spans = _pre_segment(text, resolve_profile(language))
        raw = await self._chat(
            SYSTEM_PROMPT, _build_user_prompt(spans, known_characters),
            ANALYSIS_JSON_SCHEMA, "chapter_analysis",
        )
        return _parse_llm_json(raw, spans)

    async def suggest_merges(
        self, characters: list[CharacterData]
    ) -> list[MergeSuggestion]:
        if len(characters) < 2:
            return []
        raw = await self._chat(
            MERGE_SYSTEM_PROMPT, _build_merge_prompt(characters), MERGE_JSON_SCHEMA, "merges",
        )
        return _parse_merge_json(raw, characters)


def list_openai_models(base_url: str, api_key: str | None, timeout: float = 5.0) -> list[str]:
    """Modèles exposés par le serveur (GET /models). Lève une exception si injoignable."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = httpx.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=timeout)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []) if "id" in m)
