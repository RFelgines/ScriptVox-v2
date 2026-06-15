from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.enums import AgeCategory, Gender
from app.models.entities import Character

NARRATOR_VOICE_ID: str = "narrator"

VOICE_CATALOGUE: dict[Gender, list[str]] = {
    Gender.MALE:    ["male_0", "male_1", "male_2"],
    Gender.FEMALE:  ["female_0", "female_1", "female_2"],
    Gender.NEUTRAL: ["neutral_0", "neutral_1"],
    Gender.UNKNOWN: ["neutral_0", "neutral_1"],
}


@dataclass(frozen=True)
class _VoiceMeta:
    gender: Gender | None
    age: AgeCategory
    tone_tags: frozenset[str]
    quality_tags: frozenset[str]


_CATALOGUE_META: dict[str, _VoiceMeta] = {
    "narrator":  _VoiceMeta(None,           AgeCategory.ADULT,       frozenset({"neutral", "smooth"}),    frozenset({"smooth"})),
    "male_0":    _VoiceMeta(Gender.MALE,    AgeCategory.ADULT,       frozenset({"warm", "neutral"}),      frozenset({"deep"})),
    "male_1":    _VoiceMeta(Gender.MALE,    AgeCategory.YOUNG_ADULT, frozenset({"gentle", "neutral"}),    frozenset({"smooth"})),
    "male_2":    _VoiceMeta(Gender.MALE,    AgeCategory.ELDER,       frozenset({"cold", "commanding"}),   frozenset({"deep", "raspy"})),
    "female_0":  _VoiceMeta(Gender.FEMALE,  AgeCategory.ADULT,       frozenset({"warm", "gentle"}),       frozenset({"smooth"})),
    "female_1":  _VoiceMeta(Gender.FEMALE,  AgeCategory.YOUNG_ADULT, frozenset({"neutral"}),              frozenset({"bright"})),
    "female_2":  _VoiceMeta(Gender.FEMALE,  AgeCategory.ELDER,       frozenset({"gentle"}),               frozenset({"smooth"})),
    "neutral_0": _VoiceMeta(Gender.NEUTRAL, AgeCategory.ADULT,       frozenset({"warm", "neutral"}),      frozenset({"smooth"})),
    "neutral_1": _VoiceMeta(Gender.NEUTRAL, AgeCategory.ADULT,       frozenset({"neutral"}),              frozenset({"deep"})),
}

_NARRATOR_PENALTY = -10


def _score_voice(char: Character, voice_id: str) -> int:
    """Score voice_id against character traits. Higher = better fit."""
    meta = _CATALOGUE_META[voice_id]
    if meta.gender is None:
        return _NARRATOR_PENALTY

    score = 0
    effective_gender = char.gender if char.gender != Gender.UNKNOWN else Gender.NEUTRAL
    if meta.gender == effective_gender:
        score += 4
    if char.age_category != AgeCategory.UNKNOWN and meta.age == char.age_category:
        score += 2
    if char.tone and char.tone.lower() in meta.tone_tags:
        score += 1
    if char.voice_quality and char.voice_quality.lower() in meta.quality_tags:
        score += 1
    return score


def list_catalogue_voices() -> list[tuple[str, Gender | None]]:
    """Logical voice catalogue, deterministic and de-duplicated.

    Order: narrator first (no gender), then MALE, FEMALE, NEUTRAL pools.
    NEUTRAL and UNKNOWN share neutral_0/1 in VOICE_CATALOGUE, so neutral voices
    are listed once (UNKNOWN's duplicates are skipped).
    """
    voices: list[tuple[str, Gender | None]] = [(NARRATOR_VOICE_ID, None)]
    seen: set[str] = {NARRATOR_VOICE_ID}
    for gender in (Gender.MALE, Gender.FEMALE, Gender.NEUTRAL):
        for voice_id in VOICE_CATALOGUE[gender]:
            if voice_id not in seen:
                voices.append((voice_id, gender))
                seen.add(voice_id)
    return voices


def assign_voices(book_id: int, session: Session) -> None:
    """Populate Character.voice_id using trait-based scoring (idempotent).

    Characters are processed alphabetically for determinism. Each character
    receives the highest-scoring unused voice; if all voices are taken the
    best overall voice is reused (wrap-around).
    """
    characters = session.exec(
        select(Character)
        .where(Character.book_id == book_id)
        .order_by(Character.name)
    ).all()

    candidate_ids = [vid for vid in _CATALOGUE_META if vid != NARRATOR_VOICE_ID]
    used: set[str] = {
        char.voice_id for char in characters
        if char.voice_id is not None and char.voice_id != NARRATOR_VOICE_ID
    }

    for char in characters:
        if char.voice_id is not None:
            continue

        # Score all candidates; sort DESC by score, ASC by voice_id (tie-break → determinism)
        scored = sorted(
            ((vid, _score_voice(char, vid)) for vid in candidate_ids),
            key=lambda x: (-x[1], x[0]),
        )
        top_score = scored[0][1]
        # Restrict wrap-around to the top-score tier so a MALE char never falls
        # back to a FEMALE/NEUTRAL voice when all MALE slots are taken.
        top_tier = [vid for vid, sc in scored if sc == top_score]
        chosen = next((vid for vid in top_tier if vid not in used), top_tier[0])
        char.voice_id = chosen
        used.add(chosen)
        session.add(char)

    session.commit()
