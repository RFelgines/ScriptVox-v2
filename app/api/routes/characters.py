from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.enums import VoiceKind
from app.models.entities import Character, Voice
from app.schemas.book import CharacterResponse, CharacterUpdate
from app.services.voice_assignment import NARRATOR_VOICE_ID, _CATALOGUE_META

router = APIRouter()

_VALID_CHARACTER_VOICE_IDS: frozenset[str] = frozenset(
    vid for vid in _CATALOGUE_META if vid != NARRATOR_VOICE_ID
)


def _is_assignable_voice_id(voice_id: str, session: Session) -> bool:
    """Catalogue voices (fixed set) OR an existing cloned voice (audit 2026-07-02,
    finding M3 — assign_voices could already auto-assign a cloned voice to a
    character, but this route rejected it on manual re-assignment)."""
    if voice_id in _VALID_CHARACTER_VOICE_IDS:
        return True
    cloned = session.exec(
        select(Voice).where(Voice.voice_id == voice_id, Voice.kind == VoiceKind.CLONED)
    ).first()
    return cloned is not None


@router.patch("/{character_id}", response_model=CharacterResponse)
def patch_character(
    character_id: int,
    body: CharacterUpdate,
    session: Session = Depends(get_session),
) -> CharacterResponse:
    char = session.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")
    if not _is_assignable_voice_id(body.voice_id, session):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid voice_id {body.voice_id!r}. Accepted values: catalogue voices "
                f"({sorted(_VALID_CHARACTER_VOICE_IDS)}) or an existing cloned voice_id."
            ),
        )
    char.voice_id = body.voice_id
    session.add(char)
    session.commit()
    session.refresh(char)
    return CharacterResponse.model_validate(char)
