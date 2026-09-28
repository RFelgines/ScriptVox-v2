from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.enums import VoiceKind
from app.models.entities import Character, Voice
from app.schemas.book import CharacterPreviewRequest, CharacterResponse, CharacterUpdate
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


@router.get("/{character_id}/preview")
def get_character_preview(
    character_id: int, voice_id: str, session: Session = Depends(get_session),
) -> FileResponse:
    """Aperçu déjà généré de la voix `voice_id` sur une réplique du personnage (404 sinon :
    le lancer avec POST puis réinterroger)."""
    from app.workers.tasks import character_preview_path

    char = session.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")
    path = Path(character_preview_path(session, char, voice_id))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview not generated yet.")
    return FileResponse(str(path), media_type="audio/wav", filename=path.name)


@router.post("/{character_id}/preview", status_code=202)
def request_character_preview(
    character_id: int, body: CharacterPreviewRequest, session: Session = Depends(get_session),
) -> dict:
    """Lance (tâche courte, prioritaire) la synthèse d'un aperçu de `voice_id` sur la réplique
    la plus longue du personnage ; déjà en cache -> `ready: true` sans rien relancer."""
    from app.workers.tasks import character_preview_path, generate_character_preview

    char = session.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")
    if not _is_assignable_voice_id(body.voice_id, session):
        raise HTTPException(status_code=422, detail=f"Invalid voice_id {body.voice_id!r}.")
    if Path(character_preview_path(session, char, body.voice_id)).exists():
        return {"ready": True}
    generate_character_preview(character_id, body.voice_id)
    return {"ready": False}


class VoiceDesignRequest(BaseModel):
    # Description OmniVoice (« female, elderly, low pitch »). Absente : déduite de la fiche.
    instruct: Optional[str] = Field(default=None, max_length=300)


@router.get("/{character_id}/voice-design")
def get_voice_design(character_id: int, session: Session = Depends(get_session)) -> dict:
    """Description de voix proposée pour le personnage (déduite de sa fiche : genre, âge,
    qualité de voix) et voix conçue actuelle s'il en a une. Le client l'affiche comme un
    « prompt de voix » modifiable avant de lancer la conception."""
    import json

    from app.services.tts.omnivoice import instruct_for_character
    from app.workers.tasks import DATA_DIR, designed_voice_id

    char = session.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")
    voice_id = designed_voice_id(char)
    meta = DATA_DIR / "voices" / voice_id / "design.json"
    current = json.loads(meta.read_text(encoding="utf-8")) if meta.is_file() else None
    return {
        "suggested_instruct": instruct_for_character(
            char.gender, char.age_category, char.voice_quality, char.voice_tone, char.description),
        "designed_voice_id": voice_id if current else None,
        "current_instruct": current["instruct"] if current else None,
        "assigned": char.voice_id == voice_id,
    }


@router.post("/{character_id}/voice-design", status_code=202)
def request_voice_design(
    character_id: int, body: VoiceDesignRequest, session: Session = Depends(get_session),
) -> dict:
    """Lance (tâche courte, prioritaire, GPU) la conception de la voix du personnage par
    OmniVoice, puis l'attribue au personnage. Réinterroger GET /characters/{id} : voice_id
    passe à `designed_voice_id` quand c'est fait. Nécessite le serveur OmniVoice."""
    from app.services.tts.omnivoice import instruct_for_character
    from app.workers.tasks import design_character_voice, designed_voice_id

    char = session.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")
    instruct = (body.instruct or "").strip() or instruct_for_character(
        char.gender, char.age_category, char.voice_quality, char.voice_tone, char.description)
    design_character_voice(character_id, instruct)
    return {"voice_id": designed_voice_id(char), "instruct": instruct}
