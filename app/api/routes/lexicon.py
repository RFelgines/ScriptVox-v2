"""Lexique de prononciation (voir app.services.audio.lexicon).

GET    /lexicon?book_id=N      entrées globales + celles du livre N (sans book_id : globales)
POST   /lexicon                crée une entrée (book_id absent = globale)
PATCH  /lexicon/{id}           modifie une entrée
DELETE /lexicon/{id}           supprime une entrée
POST   /lexicon/preview        texte tel qu'il sera envoyé au TTS pour un livre donné
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, or_, select

from app.core.db import get_session
from app.models import Book, LexiconEntry
from app.services.audio import lexicon

router = APIRouter()


class LexiconEntryIn(BaseModel):
    book_id: Optional[int] = None
    term: str = Field(min_length=1, max_length=200)
    replacement: str = Field(max_length=500)
    whole_word: bool = True
    case_sensitive: bool = False


class LexiconEntryPatch(BaseModel):
    term: Optional[str] = Field(default=None, min_length=1, max_length=200)
    replacement: Optional[str] = Field(default=None, max_length=500)
    whole_word: Optional[bool] = None
    case_sensitive: Optional[bool] = None


class LexiconPreviewIn(BaseModel):
    text: str = Field(max_length=5000)
    book_id: Optional[int] = None


def _check_book(book_id: int | None, session: Session) -> None:
    if book_id is not None and session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")


@router.get("", response_model=list[LexiconEntry])
def list_entries(book_id: Optional[int] = None, session: Session = Depends(get_session)):
    cond = LexiconEntry.book_id.is_(None)
    if book_id is not None:
        _check_book(book_id, session)
        cond = or_(cond, LexiconEntry.book_id == book_id)
    return session.exec(select(LexiconEntry).where(cond).order_by(LexiconEntry.term)).all()


@router.post("", response_model=LexiconEntry, status_code=201)
def create_entry(body: LexiconEntryIn, session: Session = Depends(get_session)):
    _check_book(body.book_id, session)
    if not body.term.strip():
        raise HTTPException(status_code=422, detail="term must not be blank.")
    entry = LexiconEntry(**body.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=LexiconEntry)
def patch_entry(entry_id: int, body: LexiconEntryPatch, session: Session = Depends(get_session)):
    entry = session.get(LexiconEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Lexicon entry {entry_id} not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(entry, key, value)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, session: Session = Depends(get_session)) -> None:
    entry = session.get(LexiconEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Lexicon entry {entry_id} not found.")
    session.delete(entry)
    session.commit()


@router.post("/preview")
def preview(body: LexiconPreviewIn, session: Session = Depends(get_session)) -> dict:
    _check_book(body.book_id, session)
    return {"text": lexicon.apply(body.text, lexicon.load_rules(session, body.book_id))}
