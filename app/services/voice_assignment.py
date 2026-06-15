from sqlmodel import Session, select

from app.core.enums import Gender
from app.models.entities import Character

NARRATOR_VOICE_ID: str = "narrator"

VOICE_CATALOGUE: dict[Gender, list[str]] = {
    Gender.MALE:    ["male_0", "male_1", "male_2"],
    Gender.FEMALE:  ["female_0", "female_1", "female_2"],
    Gender.NEUTRAL: ["neutral_0", "neutral_1"],
    Gender.UNKNOWN: ["neutral_0", "neutral_1"],
}


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
    """Populate Character.voice_id for all characters of a book (idempotent)."""
    characters = session.exec(
        select(Character)
        .where(Character.book_id == book_id)
        .order_by(Character.name)
    ).all()

    indices: dict[Gender, int] = {g: 0 for g in Gender}

    for char in characters:
        if char.voice_id is not None:
            continue

        pool = VOICE_CATALOGUE[char.gender]
        char.voice_id = pool[indices[char.gender] % len(pool)]
        indices[char.gender] += 1
        session.add(char)

    session.commit()
