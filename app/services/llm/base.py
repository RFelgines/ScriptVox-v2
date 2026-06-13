import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.enums import Gender, SegmentType
from app.core.exceptions import LLMParsingError

GEMINI_MAX_TOKENS = 500_000

SYSTEM_PROMPT = (
    "You are a literary analysis assistant. Analyze the provided chapter excerpt.\n\n"
    "Return ONLY valid JSON matching this exact schema — no markdown, no commentary:\n"
    "{\n"
    '  "characters": [\n'
    '    {"name": "...", "description": "...", "gender": "MALE|FEMALE|NEUTRAL|UNKNOWN", "voice_tone": "..."}\n'
    "  ],\n"
    '  "segments": [\n'
    '    {"position": 1, "text": "...", "type": "NARRATION|DIALOGUE", "character_name": null}\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Include EVERY word of the input in segments — no text may be dropped.\n"
    "- DIALOGUE: quoted speech only. NARRATION: everything else (prose, descriptions, actions).\n"
    "- character_name must exactly match a name in the characters array, or be null for NARRATION.\n"
    "- voice_tone: concise phrase, e.g. \"soft and hesitant\", \"deep and commanding\".\n"
    "- gender: infer from pronouns/context; use UNKNOWN if ambiguous."
)


@dataclass
class CharacterData:
    name: str
    description: str | None
    gender: Gender
    voice_tone: str | None


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
                gender=Gender(c.get("gender", "UNKNOWN")),
                voice_tone=c.get("voice_tone"),
            )
            for c in data.get("characters", [])
        ]
        segments = [
            SegmentData(
                position=s["position"],
                text=s["text"],
                segment_type=SegmentType(s.get("type", "NARRATION")),
                character_name=s.get("character_name"),
            )
            for s in data.get("segments", [])
        ]
    except (KeyError, ValueError) as exc:
        raise LLMParsingError(raw, exc) from exc

    return LLMChapterResult(characters=characters, segments=segments)
