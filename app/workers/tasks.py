import asyncio
import logging
import math
from datetime import datetime, timezone

from huey import SqliteHuey
from sqlmodel import Session, select

from app.config import get_settings

logger = logging.getLogger(__name__)

huey = SqliteHuey(filename=get_settings().huey_db_path)


async def _analyze_book(
    book_id: int,
    chapter_data: list[tuple[int, str]],
    engine,
) -> None:
    from sqlalchemy import delete as sa_delete

    from app.models import Book, Character, Segment
    from app.services.llm.base import GEMINI_MAX_TOKENS, _chunk_text, _merge_chunk_results
    from app.services.llm import factory as llm_factory

    settings = get_settings()
    provider = llm_factory.get_llm_provider(settings)

    budget = (
        math.floor(settings.ollama_context_tokens * 0.8)
        if settings.llm_provider == "ollama"
        else GEMINI_MAX_TOKENS
    )

    chapter_ids = [cid for cid, _ in chapter_data]

    # Idempotency: wipe any prior LLM results so retries are clean
    with Session(engine) as session:
        if chapter_ids:
            session.execute(sa_delete(Segment).where(Segment.chapter_id.in_(chapter_ids)))
        session.execute(sa_delete(Character).where(Character.book_id == book_id))
        session.commit()

    char_map: dict[str, int] = {}  # character name → Character.id (accumulated across chapters)
    n = len(chapter_data)

    for i, (chapter_id, raw_text) in enumerate(chapter_data):
        chunks = _chunk_text(raw_text, budget)
        chunk_results = [await provider.analyze(chunk) for chunk in chunks]
        merged = _merge_chunk_results(chunk_results)

        with Session(engine) as session:
            for cd in merged.characters:
                if cd.name not in char_map:
                    char = Character(
                        book_id=book_id,
                        name=cd.name,
                        description=cd.description,
                        gender=cd.gender,
                        voice_tone=cd.voice_tone,
                    )
                    session.add(char)
                    session.flush()
                    char_map[cd.name] = char.id

            for sd in merged.segments:
                char_id = char_map.get(sd.character_name) if sd.character_name else None
                session.add(Segment(
                    chapter_id=chapter_id,
                    position=sd.position,
                    text=sd.text,
                    segment_type=sd.segment_type,
                    character_id=char_id,
                ))

            book = session.get(Book, book_id)
            book.progress = 10.0 + (i + 1) / n * 50.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()


async def _synthesise_book(
    book_id: int,
    source_path: str,
    engine,
) -> str:
    from pathlib import Path as _Path

    from app.core.enums import SegmentType
    from app.models import Book, Chapter, Character, Segment
    from app.services.audio.assembler import assemble_wav
    from app.services.tts import factory as tts_factory
    from app.services.voice_assignment import NARRATOR_VOICE_ID

    settings = get_settings()
    provider = tts_factory.get_tts_provider(settings)

    with Session(engine) as session:
        chapters = session.exec(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
        ).all()
        all_segments: list = []
        for ch in chapters:
            all_segments.extend(
                session.exec(
                    select(Segment).where(Segment.chapter_id == ch.id).order_by(Segment.position)
                ).all()
            )
        char_voice: dict[int, str] = {}
        for seg in all_segments:
            if seg.character_id and seg.character_id not in char_voice:
                char = session.get(Character, seg.character_id)
                if char and char.voice_id:
                    char_voice[seg.character_id] = char.voice_id

    if not all_segments:
        return ""

    n = len(all_segments)
    wav_chunks: list[bytes] = []

    for i, seg in enumerate(all_segments):
        voice_id = (
            NARRATOR_VOICE_ID
            if seg.segment_type == SegmentType.NARRATION or seg.character_id is None
            else char_voice.get(seg.character_id, NARRATOR_VOICE_ID)
        )
        wav_chunks.append(await provider.synthesise(seg.text, voice_id))

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.progress = 60.0 + (i + 1) / n * 30.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()

    audio_path = str(_Path(source_path).with_suffix(".wav"))
    assemble_wav(wav_chunks, audio_path)
    return audio_path


def _process_book_impl(book_id: int) -> None:
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
        book.progress = 0.0
        book.updated_at = datetime.now(timezone.utc)
        session.add(book)
        session.commit()

    try:
        # ── Phase 1: EPUB ingestion ────────────────────────────────────────────
        parsed = EpubParser().parse(source_path)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.title = parsed.title
            if parsed.author:
                book.author = parsed.author
            for pc in parsed.chapters:
                session.add(Chapter(
                    book_id=book_id,
                    position=pc.position,
                    title=pc.title,
                    raw_text=pc.raw_text,
                ))
            book.progress = 10.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()
            # Collect chapter IDs while the session is still open
            chapters = session.exec(
                select(Chapter)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.position)
            ).all()
            chapter_data = [(ch.id, ch.raw_text) for ch in chapters]

        # ── Phase 2: LLM analysis (progress 10% → 60%) ────────────────────────
        asyncio.run(_analyze_book(book_id, chapter_data, engine))

        # ── Phase 3: Voice assignment ──────────────────────────────────────────
        from app.services.voice_assignment import assign_voices
        with Session(engine) as session:
            assign_voices(book_id, session)

        # ── Phase 4: TTS synthesis + audio assembly (progress 60% → 100%) ─────
        audio_path = asyncio.run(_synthesise_book(book_id, source_path, engine))

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.audio_path = audio_path if audio_path else None
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
