import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from app.core.enums import AgeCategory, Gender, SegmentType
from app.core.exceptions import LLMParsingError

_logger = logging.getLogger(__name__)
_E = TypeVar("_E", bound=Enum)

_ALIASES: dict[type, dict[str, str]] = {
    SegmentType: {
        "DIALOG": "DIALOGUE",
        "NARRATE": "NARRATION",
        "PROSE": "NARRATION",
        "NARRATOR": "NARRATION",
        "DESCRIPTION": "NARRATION",
        "ACTION": "NARRATION",
        "MONOLOGUE": "DIALOGUE",
    },
    Gender: {
        "M": "MALE",
        "F": "FEMALE",
        "N": "NEUTRAL",
        "U": "UNKNOWN",
    },
    AgeCategory: {
        "YOUNG": "YOUNG_ADULT",
        "TEEN": "YOUNG_ADULT",
        "TEENAGER": "YOUNG_ADULT",
        "ADOLESCENT": "YOUNG_ADULT",
        "KID": "CHILD",
        "BABY": "CHILD",
        "INFANT": "CHILD",
        "TODDLER": "CHILD",
        "OLD": "ELDER",
        "ELDERLY": "ELDER",
        "SENIOR": "ELDER",
        "AGED": "ELDER",
    },
}


def _coerce_enum(raw: str, enum_cls: type[_E], default: _E) -> _E:
    """Normalise une valeur brute LLM en membre d'enum ; retombe sur *default* avec WARNING."""
    # Normaliser : upper, espaces/tirets → underscore, supprimer la ponctuation résiduelle
    step = re.sub(r"[\s\-]+", "_", raw.strip().upper())
    normalized = re.sub(r"[^A-Z_]", "", step)

    # 1. Correspondance directe après normalisation
    try:
        return enum_cls(normalized)
    except ValueError:
        pass

    # 2. Premier token (gère "DIALOG_" issu de "DIALOG, ")
    first_token = normalized.split("_")[0] if normalized else ""
    if first_token and first_token != normalized:
        try:
            return enum_cls(first_token)
        except ValueError:
            pass

    # 3. Table d'alias (normalized puis premier token)
    aliases = _ALIASES.get(enum_cls, {})
    for candidate in (normalized, first_token):
        if candidate in aliases:
            try:
                result = enum_cls(aliases[candidate])
                _logger.warning("_coerce_enum: %r -> %s.%s (alias)", raw, enum_cls.__name__, result.value)
                return result
            except ValueError:
                pass

    # 4. Défaut
    _logger.warning("_coerce_enum: %r unrecognized for %s, defaulting to %s", raw, enum_cls.__name__, default.value)
    return default

GEMINI_MAX_TOKENS = 500_000

SYSTEM_PROMPT = (
    "You are a literary analysis assistant. Analyze the provided chapter excerpt.\n\n"
    "Return ONLY valid JSON matching this exact schema — no markdown, no commentary:\n"
    "{\n"
    '  "characters": [\n'
    '    {\n'
    '      "name": "...", "description": "...",\n'
    '      "gender": "MALE|FEMALE|NEUTRAL|UNKNOWN",\n'
    '      "age_category": "CHILD|YOUNG_ADULT|ADULT|ELDER|UNKNOWN",\n'
    '      "tone": "...", "voice_quality": "...", "voice_tone": "..."\n'
    '    }\n'
    "  ],\n"
    '  "segments": [\n'
    '    {"position": 1, "text": "...", "type": "NARRATION|DIALOGUE", "character_name": null}\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Include EVERY word of the input in segments — no text may be dropped.\n"
    "- DIALOGUE: quoted speech only. NARRATION: everything else (prose, descriptions, actions).\n"
    "- character_name must exactly match a name in the characters array, or be null for NARRATION.\n"
    "- gender: infer from pronouns/context; use UNKNOWN if ambiguous.\n"
    "- age_category: infer from apparent age (CHILD <13, YOUNG_ADULT 13-25, ADULT 26-60, ELDER 60+); use UNKNOWN if ambiguous.\n"
    "- tone: single word for emotional/personality quality, e.g. \"warm\", \"cold\", \"harsh\", \"gentle\".\n"
    "- voice_quality: single word for acoustic quality, e.g. \"deep\", \"raspy\", \"bright\", \"smooth\".\n"
    "- voice_tone: concise phrase combining tone and quality, e.g. \"soft and hesitant\", \"deep and commanding\"."
)


@dataclass
class CharacterData:
    name: str
    description: str | None
    gender: Gender
    age_category: AgeCategory = AgeCategory.UNKNOWN
    tone: str | None = None
    voice_quality: str | None = None
    voice_tone: str | None = None


@dataclass
class SegmentData:
    position: int
    text: str
    segment_type: SegmentType
    character_name: str | None


@dataclass
class LLMChapterResult:
    characters: list[CharacterData]
    segments: list[SegmentData]


class BaseLLMProvider(ABC):
    @abstractmethod
    async def analyze(self, text: str) -> LLMChapterResult: ...


# ── Pre-segmentation (label-based protocol, ARCHITECTURE.md §2.7) ────────────────

_DIALOGUE_RE = re.compile(
    "|".join((
        r"«[^»]*»",              # guillemets français
        r"“[^”]*”",              # guillemets typographiques
        r'"[^"]*"',              # guillemets droits
        r"^[ \t]*[—–―][^\n]*",   # ligne ouverte par un tiret cadratin (dialogue FR)
    )),
    re.MULTILINE,
)


@dataclass
class _Span:
    index: int
    text: str
    is_dialogue: bool


def _pre_segment(text: str) -> list[_Span]:
    """Découpe *text* en spans ordonnés narration/dialogue, byte-exact (zéro mot perdu).

    Invariant : ``"".join(s.text for s in _pre_segment(t)) == t``.
    Le type (dialogue vs narration) est déterminé ici via les délimiteurs ; le LLM
    n'attribue qu'un locuteur aux spans de dialogue (cf. §2.7). Un dialogue non
    détecté reste narration (lu par le narrateur) — jamais de crash, jamais de perte.
    """
    spans: list[_Span] = []
    idx = 0
    pos = 0
    for match in _DIALOGUE_RE.finditer(text):
        start, end = match.span()
        if start > pos:
            idx += 1
            spans.append(_Span(idx, text[pos:start], False))
        idx += 1
        spans.append(_Span(idx, text[start:end], True))
        pos = end
    if pos < len(text):
        idx += 1
        spans.append(_Span(idx, text[pos:], False))
    if not spans:
        spans.append(_Span(1, text, False))
    return spans


def _build_user_prompt(spans: list[_Span]) -> str:
    """Rend les spans numérotés et tagués pour le LLM : ``[i][DIALOGUE|NARRATION] texte``.

    Le texte est normalisé (espaces/sauts de ligne compactés) ; les spans vides après
    normalisation sont omis de l'affichage mais conservent leur index d'origine.
    """
    lines: list[str] = []
    for span in spans:
        display = " ".join(span.text.split())
        if not display:
            continue
        tag = "DIALOGUE" if span.is_dialogue else "NARRATION"
        lines.append(f"[{span.index}][{tag}] {display}")
    return "\n".join(lines)


# ── Token budgeting ────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _split_by_sep(text: str, sep: str, max_tokens: int) -> list[str]:
    parts = [p for p in text.split(sep) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for part in parts:
        part_tokens = _estimate_tokens(part)
        if part_tokens > max_tokens:
            # Single unit overflows — recurse to finer granularity
            if current:
                chunks.append(sep.join(current))
                current = []
                current_tokens = 0
            if sep == "\n\n":
                chunks.extend(_split_by_sep(part, "\n", max_tokens))
            else:
                chunks.append(part)  # single line too long — accept as-is
        elif current_tokens + part_tokens > max_tokens and current:
            chunks.append(sep.join(current))
            current = [part]
            current_tokens = part_tokens
        else:
            current.append(part)
            current_tokens += part_tokens

    if current:
        chunks.append(sep.join(current))

    return chunks or [text]


def _chunk_text(text: str, max_tokens: int) -> list[str]:
    if _estimate_tokens(text) <= max_tokens:
        return [text]
    return _split_by_sep(text, "\n\n", max_tokens)


# ── Result helpers ─────────────────────────────────────────────────────────────

def _merge_chunk_results(results: list[LLMChapterResult]) -> LLMChapterResult:
    seen: dict[str, CharacterData] = {}
    segments: list[SegmentData] = []
    pos = 0

    for result in results:
        for cd in result.characters:
            if cd.name not in seen:
                seen[cd.name] = cd
        for sd in result.segments:
            pos += 1
            segments.append(SegmentData(
                position=pos,
                text=sd.text,
                segment_type=sd.segment_type,
                character_name=sd.character_name,
            ))

    return LLMChapterResult(characters=list(seen.values()), segments=segments)


def _parse_llm_json(raw: str) -> LLMChapterResult:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMParsingError(raw, exc) from exc

    try:
        characters = [
            CharacterData(
                name=c["name"],
                description=c.get("description"),
                gender=_coerce_enum(c.get("gender", "UNKNOWN"), Gender, Gender.UNKNOWN),
                age_category=_coerce_enum(c.get("age_category", "UNKNOWN"), AgeCategory, AgeCategory.UNKNOWN),
                tone=c.get("tone"),
                voice_quality=c.get("voice_quality"),
                voice_tone=c.get("voice_tone"),
            )
            for c in data.get("characters", [])
        ]
        segments = [
            SegmentData(
                position=s["position"],
                text=s["text"],
                segment_type=_coerce_enum(s.get("type", "NARRATION"), SegmentType, SegmentType.NARRATION),
                character_name=s.get("character_name"),
            )
            for s in data.get("segments", [])
        ]
    except (KeyError, ValueError) as exc:
        raise LLMParsingError(raw, exc) from exc

    return LLMChapterResult(characters=characters, segments=segments)
