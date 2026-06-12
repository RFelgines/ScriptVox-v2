import logging
from datetime import datetime, timezone

from huey import SqliteHuey

from app.config import get_settings

logger = logging.getLogger(__name__)

huey = SqliteHuey(filename=get_settings().huey_db_path)


def _process_book_impl(book_id: int) -> None:
    from sqlmodel import Session

    from app.core.db import get_engine
    from app.core.enums import BookStatus
    from app.models import Book, Chapter
    from app.services.epub.parser import EpubParser

    engine = get_engine()

    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None:
            logger.error("process_book called with unknown book_id=%d", book_id)
            return
        source_path = book.source_path
        book.status = BookStatus.PROCESSING
        book.updated_at = datetime.now(timezone.utc)
        session.add(book)
        session.commit()

    try:
        parsed = EpubParser().parse(source_path)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.title = parsed.title
            if parsed.author:
                book.author = parsed.author
            for pc in parsed.chapters:
                session.add(
                    Chapter(
                        book_id=book_id,
                        position=pc.position,
                        title=pc.title,
                        raw_text=pc.raw_text,
                    )
                )
            book.status = BookStatus.DONE
            book.progress = 100.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()

    except Exception as exc:
        logger.exception("process_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                book.updated_at = datetime.now(timezone.utc)
                session.add(book)
                session.commit()


@huey.task()
def process_book(book_id: int) -> None:
    _process_book_impl(book_id)
