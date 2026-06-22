from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.enums import MergeSuggestionStatus
from app.models import Character, CharacterMergeSuggestion, Segment
from app.schemas.book import MergeSuggestionResponse

router = APIRouter()


def _get_pending_suggestion(suggestion_id: int, session: Session) -> CharacterMergeSuggestion:
    suggestion = session.get(CharacterMergeSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail=f"Merge suggestion {suggestion_id} not found.")
    if suggestion.status != MergeSuggestionStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Merge suggestion {suggestion_id} already resolved (status={suggestion.status.value}).",
        )
    return suggestion


@router.post("/{suggestion_id}/accept", response_model=MergeSuggestionResponse)
def accept_merge_suggestion(
    suggestion_id: int, session: Session = Depends(get_session)
) -> MergeSuggestionResponse:
    suggestion = _get_pending_suggestion(suggestion_id, session)

    merged_char = session.get(Character, suggestion.merged_character_id)
    if merged_char is not None:
        for seg in session.exec(
            select(Segment).where(Segment.character_id == suggestion.merged_character_id)
        ).all():
            seg.character_id = suggestion.survivor_character_id
            session.add(seg)
        # Flush la réassignation avant le delete : sans ça, SQLAlchemy recharge la
        # collection `merged_char.segments` depuis la DB (encore non flushée) pendant
        # le traitement de la suppression et écrase character_id avec NULL (cascade
        # par défaut "disassociate before delete" sur la relation sans cascade=delete).
        session.flush()
        session.delete(merged_char)

    # Les autres suggestions PENDING référençant le personnage qui disparaît
    # deviennent caduques (ex. groupe de 3+ doublons) — on les rejette pour éviter
    # une référence morte plutôt que de les laisser pointer vers un Character supprimé.
    stale = session.exec(
        select(CharacterMergeSuggestion).where(
            CharacterMergeSuggestion.book_id == suggestion.book_id,
            CharacterMergeSuggestion.status == MergeSuggestionStatus.PENDING,
            CharacterMergeSuggestion.id != suggestion.id,
            (CharacterMergeSuggestion.survivor_character_id == suggestion.merged_character_id)
            | (CharacterMergeSuggestion.merged_character_id == suggestion.merged_character_id),
        )
    ).all()
    for s in stale:
        s.status = MergeSuggestionStatus.REJECTED
        session.add(s)

    suggestion.status = MergeSuggestionStatus.ACCEPTED
    session.add(suggestion)
    session.commit()
    session.refresh(suggestion)
    return MergeSuggestionResponse.model_validate(suggestion)


@router.post("/{suggestion_id}/reject", response_model=MergeSuggestionResponse)
def reject_merge_suggestion(
    suggestion_id: int, session: Session = Depends(get_session)
) -> MergeSuggestionResponse:
    suggestion = _get_pending_suggestion(suggestion_id, session)
    suggestion.status = MergeSuggestionStatus.REJECTED
    session.add(suggestion)
    session.commit()
    session.refresh(suggestion)
    return MergeSuggestionResponse.model_validate(suggestion)
