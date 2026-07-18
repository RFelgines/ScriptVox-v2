from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.enums import ChapterStatus
from app.models import Book, Chapter
from app.schemas.book import QueueItemResponse

router = APIRouter()


@router.get("/queue", response_model=list[QueueItemResponse])
def get_queue(session: Session = Depends(get_session)) -> list[QueueItemResponse]:
    """Global cross-book view of chapters awaiting or undergoing generation —
    GENERATING first (there is at most one, given the single Huey worker), then
    PENDING **and actually queued** (queued_at set by a real dispatch — see
    Chapter.queued_at, Lot 3 audit 2026-07-11) ordered by priority (desc) so the
    frontend can display and reorder what will run next. A PENDING chapter never
    dispatched isn't "queued" in any real sense and is omitted, same as
    DONE/FAILED chapters."""
    rows = session.exec(
        select(Chapter, Book.title)
        .join(Book, Book.id == Chapter.book_id)
        .where(
            or_(
                Chapter.status == ChapterStatus.GENERATING,
                and_(Chapter.status == ChapterStatus.PENDING, Chapter.queued_at.is_not(None)),
            )
        )
        .order_by(
            (Chapter.status != ChapterStatus.GENERATING),
            Chapter.priority.desc(),
            Chapter.book_id,
            Chapter.position,
        )
    ).all()
    return [
        QueueItemResponse(
            chapter_id=chapter.id,
            book_id=chapter.book_id,
            book_title=book_title,
            position=chapter.position,
            title=chapter.title,
            status=chapter.status,
            priority=chapter.priority,
            error_message=chapter.error_message,
        )
        for chapter, book_title in rows
    ]
