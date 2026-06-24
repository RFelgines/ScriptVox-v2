from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.enums import AgeCategory, Gender, VoiceKind
from app.models.entities import Character, Voice

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


def _humanize_voice_id(voice_id: str) -> str:
    return voice_id.replace("_", " ").title()


def seed_catalogue_voices(session: Session) -> None:
    """Insert any catalogue voice missing from the Voice table (idempotent).

    Voice is the user-facing source of truth (onglet Voix, favoris) ; ce
    seed la peuple depuis list_catalogue_voices() sans toucher à
    assign_voices/_score_voice, qui continuent d'utiliser VOICE_CATALOGUE /
    _CATALOGUE_META directement pour l'attribution automatique.
    """
    existing = {v.voice_id for v in session.exec(select(Voice)).all()}
    for voice_id, gender in list_catalogue_voices():
        if voice_id in existing:
            continue
        session.add(Voice(
            voice_id=voice_id,
            name=_humanize_voice_id(voice_id),
            kind=VoiceKind.CATALOGUE,
            gender=gender,
        ))
    session.commit()


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

        # Restrict candidates to the character's gender pool so a MALE char
        # never falls back to a FEMALE/NEUTRAL voice. Rank by fit (DESC score,
        # ASC voice_id tie-break) and take the best UNUSED one — falling
        # through to the next-best free voice of the same gender instead of
        # collapsing onto the single top pick when it's already taken. Only
        # reuse (ranked[0]) once the whole gender pool is exhausted.
        effective_gender = char.gender if char.gender != Gender.UNKNOWN else Gender.NEUTRAL
        pool = VOICE_CATALOGUE.get(effective_gender) or candidate_ids
        ranked = sorted(pool, key=lambda vid: (-_score_voice(char, vid), vid))
        chosen = next((vid for vid in ranked if vid not in used), ranked[0])
        char.voice_id = chosen
        used.add(chosen)
        session.add(char)

    session.commit()
