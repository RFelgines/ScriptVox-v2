import mimetypes
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.enums import BookStatus, ChapterStatus, MergeSuggestionStatus
from app.models import Book, Chapter, Character, CharacterMergeSuggestion
from app.schemas.book import BookResponse, ChapterResponse, CharacterResponse, MergeSuggestionResponse
from app.workers.tasks import analyze_book, generate_book, generate_chapter

DATA_DIR = Path("data")

_ALLOWED_COVER_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

router = APIRouter()


@router.post("", response_model=BookResponse, status_code=202)
async def upload_book(
    file: UploadFile = File(...),
    author: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> BookResponse:
    if not file.filename or not file.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=422, detail="Only .epub files are accepted.")

    DATA_DIR.mkdir(exist_ok=True)
    dest = DATA_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    dest.write_bytes(await file.read())

    book = Book(
        title=file.filename.removesuffix(".epub"),
        author=author,
        source_path=str(dest),
    )
    session.add(book)
    session.commit()
    session.refresh(book)

    analyze_book(book.id)

    return BookResponse.model_validate(book)


@router.get("", response_model=list[BookResponse])
def list_books(session: Session = Depends(get_session)) -> list[BookResponse]:
    return [BookResponse.model_validate(b) for b in session.exec(select(Book)).all()]


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, session: Session = Depends(get_session)) -> BookResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    return BookResponse.model_validate(book)


@router.post("/{book_id}/generate", response_model=BookResponse, status_code=202)
def trigger_generate(book_id: int, session: Session = Depends(get_session)) -> BookResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    if book.status != BookStatus.ANALYZED:
        raise HTTPException(
            status_code=409,
            detail=f"Book {book_id} cannot be generated (status={book.status.value}). Expected ANALYZED.",
        )
    generate_book(book.id)
    return BookResponse.model_validate(book)


@router.get("/{book_id}/audio")
def get_book_audio(book_id: int, session: Session = Depends(get_session)) -> FileResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    if not book.audio_path:
        raise HTTPException(status_code=404, detail="Audio not ready — book is still processing or failed.")
    path = Path(book.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk.")
    return FileResponse(str(path), media_type="audio/wav", filename=path.name)


@router.get("/{book_id}/audio/mp3")
def get_book_mp3(book_id: int, session: Session = Depends(get_session)) -> FileResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    if not book.mp3_path:
        raise HTTPException(status_code=404, detail="MP3 not ready — generate the book first.")
    path = Path(book.mp3_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="MP3 file not found on disk.")
    return FileResponse(str(path), media_type="audio/mpeg", filename=path.name)


@router.get("/{book_id}/cover")
def get_book_cover(book_id: int, session: Session = Depends(get_session)) -> FileResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    if not book.cover_path:
        raise HTTPException(status_code=404, detail="No cover available for this book.")
    path = Path(book.cover_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover file not found on disk.")
    media_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return FileResponse(str(path), media_type=media_type, filename=path.name)


@router.post("/{book_id}/cover", response_model=BookResponse)
async def upload_book_cover(
    book_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> BookResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    content_type = file.content_type or ""
    ext = _ALLOWED_COVER_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported image type '{content_type}'. "
                f"Allowed: {', '.join(_ALLOWED_COVER_TYPES)}."
            ),
        )
    cover_dir = DATA_DIR / str(book_id)
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / f"cover{ext}"
    cover_path.write_bytes(await file.read())
    book.cover_path = str(cover_path)
    session.add(book)
    session.commit()
    session.refresh(book)
    return BookResponse.model_validate(book)


@router.post("/{book_id}/chapters/{position}/generate", response_model=ChapterResponse, status_code=202)
def trigger_chapter_generate(
    book_id: int,
    position: int,
    session: Session = Depends(get_session),
) -> ChapterResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    if book.status != BookStatus.ANALYZED:
        raise HTTPException(
            status_code=409,
            detail=f"Book {book_id} is not ready for chapter generation (status={book.status.value}). Expected ANALYZED.",
        )
    chapter = session.exec(
        select(Chapter).where(Chapter.book_id == book_id, Chapter.position == position)
    ).first()
    if chapter is None:
        raise HTTPException(
            status_code=404, detail=f"Chapter {position} not found for book {book_id}."
        )
    generate_chapter(chapter.id)
    return ChapterResponse.model_validate(chapter)


@router.post("/{book_id}/chapters/generate", response_model=list[ChapterResponse], status_code=202)
def trigger_all_chapters_generate(
    book_id: int,
    session: Session = Depends(get_session),
) -> list[ChapterResponse]:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    if book.status != BookStatus.ANALYZED:
        raise HTTPException(
            status_code=409,
            detail=f"Book {book_id} is not ready for chapter generation (status={book.status.value}). Expected ANALYZED.",
        )
    chapters = session.exec(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
    ).all()
    for chapter in chapters:
        if chapter.status != ChapterStatus.DONE:
            generate_chapter(chapter.id)
    return [ChapterResponse.model_validate(c) for c in chapters]


@router.get("/{book_id}/chapters", response_model=list[ChapterResponse])
def list_chapters(book_id: int, session: Session = Depends(get_session)) -> list[ChapterResponse]:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    chapters = session.exec(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
    ).all()
    return [ChapterResponse.model_validate(c) for c in chapters]


@router.get("/{book_id}/chapters/{position}/audio")
def get_chapter_audio(
    book_id: int,
    position: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    chapter = session.exec(
        select(Chapter).where(Chapter.book_id == book_id, Chapter.position == position)
    ).first()
    if chapter is None:
        raise HTTPException(
            status_code=404, detail=f"Chapter {position} not found for book {book_id}."
        )
    if chapter.status != ChapterStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Chapter {position} audio is not ready (status={chapter.status.value}). "
                f"Use POST /books/{book_id}/chapters/{position}/generate first."
            ),
        )
    path = Path(chapter.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk.")
    return FileResponse(str(path), media_type="audio/wav", filename=path.name)


@router.get("/{book_id}/characters", response_model=list[CharacterResponse])
def get_book_characters(book_id: int, session: Session = Depends(get_session)) -> list[CharacterResponse]:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    characters = session.exec(select(Character).where(Character.book_id == book_id)).all()
    return [CharacterResponse.model_validate(c) for c in characters]


@router.get("/{book_id}/merge-suggestions", response_model=list[MergeSuggestionResponse])
def get_book_merge_suggestions(
    book_id: int, session: Session = Depends(get_session)
) -> list[MergeSuggestionResponse]:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    suggestions = session.exec(
        select(CharacterMergeSuggestion).where(
            CharacterMergeSuggestion.book_id == book_id,
            CharacterMergeSuggestion.status == MergeSuggestionStatus.PENDING,
        )
    ).all()
    return [MergeSuggestionResponse.model_validate(s) for s in suggestions]


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int, session: Session = Depends(get_session)) -> None:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found.")
    paths = (book.source_path, book.audio_path, book.mp3_path)
    session.delete(book)
    session.commit()
    for path in paths:
        if path and os.path.exists(path):
            os.remove(path)
    shutil.rmtree(DATA_DIR / str(book_id), ignore_errors=True)
