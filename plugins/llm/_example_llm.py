"""Template d'un plugin LLM. Copier en `mon_llm.py` (sans le `_`) puis l'adapter.

Contrat : PROVIDER_NAME + create(settings, options) -> provider (sous-classe de BaseLLMProvider).

Le provider reçoit un chapitre déjà découpé en « spans » numérotés et étiquetés
([1][NARRATION] …, [2][DIALOGUE] …) et doit renvoyer un JSON {"characters": [...],
"attributions": [...]} : les helpers de app.services.llm.base font tout le reste (pré-découpage,
schéma JSON, réparation des noms, reconstruction des segments). Le plus simple est donc de
n'écrire QUE l'appel réseau vers votre modèle, comme ci-dessous.
"""
from app.core.exceptions import LLMRequestError
from app.services.llm.base import (
    ANALYSIS_JSON_SCHEMA,
    BaseLLMProvider,
    MERGE_JSON_SCHEMA,
    MERGE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    _build_merge_prompt,
    _build_user_prompt,
    _parse_llm_json,
    _parse_merge_json,
    _pre_segment,
)
from app.services.llm.language_profiles import resolve_profile

PROVIDER_NAME = "mon_llm"
DESCRIPTION = "Exemple de moteur LLM"


async def ask_my_model(system: str, user: str, schema: dict, model: str) -> str:
    """À REMPLACER : appelez votre modèle et renvoyez le texte JSON de sa réponse.
    `schema` est le JSON Schema attendu (à transmettre si votre moteur sait contraindre la sortie)."""
    raise NotImplementedError("brancher ici l'appel à votre modèle")


class MonLLM(BaseLLMProvider):
    chunk_tokens = 12_000  # budget par appel : les chapitres plus longs sont découpés

    def __init__(self, model: str):
        self.model = model

    async def analyze(self, text, known_characters=None, language=None):
        spans = _pre_segment(text, resolve_profile(language))
        try:
            raw = await ask_my_model(
                SYSTEM_PROMPT, _build_user_prompt(spans, known_characters),
                ANALYSIS_JSON_SCHEMA, self.model,
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_llm_json(raw, spans)

    async def suggest_merges(self, characters):
        if len(characters) < 2:
            return []
        try:
            raw = await ask_my_model(
                MERGE_SYSTEM_PROMPT, _build_merge_prompt(characters), MERGE_JSON_SCHEMA, self.model,
            )
        except Exception as exc:
            raise LLMRequestError(exc) from exc
        return _parse_merge_json(raw, characters)

    def unload(self) -> None:
        """Facultatif : libérer la mémoire côté serveur à la fin de l'analyse."""


def list_models(settings, options):
    """Facultatif : suggestions de la liste « Modèle » de Paramètres."""
    return ["mon-modele"]


def create(settings, options):
    return MonLLM(options.get("model", "mon-modele"))
