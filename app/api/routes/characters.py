from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session
from app.models.entities import Character
from app.schemas.book import CharacterResponse, CharacterUpdate
from app.services.voice_assignment import NARRATOR_VOICE_ID, _CATALOGUE_META

router = APIRouter()

_VALID_CHARACTER_VOICE_IDS: frozenset[str] = frozenset(
    vid for vid in _CATALOGUE_META if vid != NARRATOR_VOICE_ID
)


@router.patch("/{character_id}", response_model=CharacterResponse)
def patch_character(
    character_id: int,
    body: CharacterUpdate,
    session: Session = Depends(get_session),
) -> CharacterResponse:
    char = session.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")
    if body.voice_id not in _VALID_CHARACTER_VOICE_IDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid voice_id {body.voice_id!r}. "
                f"Accepted values: {sorted(_VALID_CHARACTER_VOICE_IDS)}"
            ),
        )
    char.voice_id = body.voice_id
    session.add(char)
    session.commit()
    session.refresh(char)
    return CharacterResponse.model_validate(char)
