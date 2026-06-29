import asyncio
import logging
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

    from app.core.enums import BookStatus
    from app.models import Book, Character, CharacterMergeSuggestion, Segment
    from app.services.llm.base import (
        GEMINI_MAX_TOKENS,
        CharacterData,
        _chunk_text,
        _merge_chunk_results,
    )
    from app.services.llm import factory as llm_factory

    settings = get_settings()
    provider = llm_factory.get_llm_provider(settings)

    budget = (
        settings.ollama_chunk_tokens
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
        # Abort if the user triggered /stop while we were processing a previous chapter
        if i > 0:
            with Session(engine) as _s:
                _b = _s.get(Book, book_id)
                if _b is None or _b.status == BookStatus.FAILED:
                    logger.info("analyze_book: stop requested at chapter %d, aborting", i)
                    return

        known = list(char_map.keys())
        chunks = _chunk_text(raw_text, budget)

        _MAX_RETRIES = 3
        _RETRY_DELAY = 30  # seconds — gives Ollama time to recover from OOM/timeout
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                chunk_results = [await provider.analyze(chunk, known) for chunk in chunks]
                merged = _merge_chunk_results(chunk_results)
                if attempt > 0:
                    logger.info(
                        "analyze_book: book_id=%d chapter %d/%d succeeded on attempt %d",
                        book_id, i + 1, n, attempt + 1,
                    )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "analyze_book: book_id=%d chapter %d/%d attempt %d/%d failed: %s",
                    book_id, i + 1, n, attempt + 1, _MAX_RETRIES, exc,
                )
                if attempt < _MAX_RETRIES - 1:
                    with Session(engine) as _s:
                        _b = _s.get(Book, book_id)
                        if _b:
                            _b.error_message = (
                                f"[ch {i + 1}/{n} essai {attempt + 1}/{_MAX_RETRIES}] "
                                f"{type(exc).__name__}: {exc} — nouvel essai dans {_RETRY_DELAY}s"
                            )
                            _s.add(_b)
                            _s.commit()
                    await asyncio.sleep(_RETRY_DELAY)
        if last_exc is not None:
            raise last_exc

        with Session(engine) as session:
            for cd in merged.characters:
                if cd.name not in char_map:
                    char = Character(
                        book_id=book_id,
                        name=cd.name,
                        description=cd.description,
                        gender=cd.gender,
                        age_category=cd.age_category,
                        tone=cd.tone,
                        voice_quality=cd.voice_quality,
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
                    emotion=sd.emotion,
                ))

            book = session.get(Book, book_id)
            book.progress = 10.0 + (i + 1) / n * 50.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()

    # ── Suggestions de fusion de personnages (livre entier, LLM déjà chaud) ──────
    # Non bloquant : un échec ici n'empêche pas le livre de passer à ANALYZED.
    with Session(engine) as session:
        characters = session.exec(select(Character).where(Character.book_id == book_id)).all()

    if len(characters) >= 2:
        char_data = [
            CharacterData(
                name=c.name,
                description=c.description,
                gender=c.gender,
                age_category=c.age_category,
                tone=c.tone,
                voice_quality=c.voice_quality,
                voice_tone=c.voice_tone,
            )
            for c in characters
        ]
        try:
            suggestions = await provider.suggest_merges(char_data)
        except Exception:
            logger.exception("suggest_merges failed for book_id=%s (non-blocking)", book_id)
            suggestions = []

        if suggestions:
            name_to_id = {c.name: c.id for c in characters}
            with Session(engine) as session:
                for sug in suggestions:
                    session.add(CharacterMergeSuggestion(
                        book_id=book_id,
                        survivor_character_id=name_to_id[sug.survivor_name],
                        merged_character_id=name_to_id[sug.merged_name],
                        reason=sug.reason,
                    ))
                session.commit()


async def _synthesise_book(
    book_id: int,
    source_path: str,
    engine,
) -> str:
    from pathlib import Path as _Path

    from app.core.enums import SegmentType
    from app.models import Book, Chapter, Character, Segment, Voice
    from app.services.audio.assembler import assemble_wav
    from app.services.tts import factory as tts_factory
    from app.services.voice_assignment import NARRATOR_VOICE_ID

    settings = get_settings()

    with Session(engine) as session:
        book = session.get(Book, book_id)
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

        # Look up reference_audio_path once per unique voice_id (one query per voice, not per segment)
        all_voice_ids: set[str] = set(char_voice.values()) | {NARRATOR_VOICE_ID}
        ref_path: dict[str, str | None] = {}
        for vid in all_voice_ids:
            v = session.exec(select(Voice).where(Voice.voice_id == vid)).first()
            ref_path[vid] = v.reference_audio_path if v else None

    if not all_segments:
        return ""

    provider = tts_factory.get_tts_provider(settings, override=book.tts_provider if book else None)
    n = len(all_segments)
    wav_chunks: list[bytes] = []

    for i, seg in enumerate(all_segments):
        voice_id = (
            NARRATOR_VOICE_ID
            if seg.segment_type == SegmentType.NARRATION or seg.character_id is None
            else char_voice.get(seg.character_id, NARRATOR_VOICE_ID)
        )
        wav_chunks.append(await provider.synthesise(
            seg.text, voice_id,
            emotion=seg.emotion,
            reference_audio_path=ref_path.get(voice_id),
        ))

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.progress = 60.0 + (i + 1) / n * 30.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()

    audio_path = str(_Path(source_path).with_suffix(".wav"))
    assemble_wav(wav_chunks, audio_path)
    return audio_path


def _analyze_book_impl(book_id: int) -> None:
    from app.core.db import get_engine
    from app.core.enums import BookStatus
    from app.models import Book, Chapter
    from app.services.epub.parser import EpubParser
    from app.services.voice_assignment import assign_voices

    engine = get_engine()

    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None:
            logger.error("analyze_book called with unknown book_id=%d", book_id)
            return
        source_path = book.source_path
        book.status = BookStatus.PROCESSING
        book.progress = 0.0
        book.error_message = None
        book.updated_at = datetime.now(timezone.utc)
        session.add(book)
        session.commit()

    try:
        # ── Nettoyage idempotent (re-analyse) ──────────────────────────────────
        from sqlalchemy import delete as sa_delete
        from app.models import Character, CharacterMergeSuggestion, Segment

        with Session(engine) as session:
            existing_ids = list(
                session.exec(select(Chapter.id).where(Chapter.book_id == book_id)).all()
            )
            if existing_ids:
                session.execute(sa_delete(Segment).where(Segment.chapter_id.in_(existing_ids)))
                session.execute(sa_delete(Chapter).where(Chapter.book_id == book_id))
            session.execute(sa_delete(CharacterMergeSuggestion).where(CharacterMergeSuggestion.book_id == book_id))
            session.execute(sa_delete(Character).where(Character.book_id == book_id))
            session.commit()

        # ── EPUB ingestion ─────────────────────────────────────────────────────
        parsed = EpubParser().parse(source_path)

        with Session(engine) as session:
            from pathlib import Path as _Path
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
            if parsed.cover_image:
                _COVER_EXT = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                    "image/webp": ".webp",
                }
                ext = _COVER_EXT.get(parsed.cover_media_type or "", ".jpg")
                cover_dir = _Path("data") / str(book_id)
                cover_dir.mkdir(parents=True, exist_ok=True)
                cover_file = cover_dir / f"cover{ext}"
                cover_file.write_bytes(parsed.cover_image)
                book.cover_path = str(cover_file)
            book.progress = 10.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()
            chapters = session.exec(
                select(Chapter)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.position)
            ).all()
            chapter_data = [(ch.id, ch.raw_text) for ch in chapters]

        # ── LLM analysis (progress 10% → 60%) ─────────────────────────────────
        asyncio.run(_analyze_book(book_id, chapter_data, engine))

        # ── Voice assignment ───────────────────────────────────────────────────
        with Session(engine) as session:
            assign_voices(book_id, session, tts_provider=get_settings().tts_provider)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.status = BookStatus.ANALYZED
            book.progress = 100.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()

    except Exception as exc:
        logger.exception("analyze_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                book.updated_at = datetime.now(timezone.utc)
                session.add(book)
                session.commit()


def _generate_book_impl(book_id: int) -> None:
    from app.core.db import get_engine
    from app.core.enums import BookStatus
    from app.models import Book

    engine = get_engine()

    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None:
            logger.error("generate_book called with unknown book_id=%d", book_id)
            return
        if book.status not in (BookStatus.ANALYZED, BookStatus.DONE):
            logger.warning(
                "generate_book skipped: book_id=%d has status=%s", book_id, book.status
            )
            return
        source_path = book.source_path
        book.status = BookStatus.GENERATING
        book.progress = 0.0
        book.error_message = None
        book.updated_at = datetime.now(timezone.utc)
        session.add(book)
        session.commit()

    try:
        # ── TTS synthesis + audio assembly (progress 60% → 90%) ───────────────
        audio_path = asyncio.run(_synthesise_book(book_id, source_path, engine))

        mp3_path: str | None = None
        if audio_path:
            from pathlib import Path as _Path
            from app.services.audio.assembler import wav_to_mp3
            mp3_bytes = wav_to_mp3(_Path(audio_path).read_bytes())
            mp3_file = _Path(audio_path).with_suffix(".mp3")
            mp3_file.write_bytes(mp3_bytes)
            mp3_path = str(mp3_file)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.audio_path = audio_path if audio_path else None
            book.mp3_path = mp3_path
            book.status = BookStatus.DONE
            book.progress = 100.0
            book.updated_at = datetime.now(timezone.utc)
            session.add(book)
            session.commit()

    except Exception as exc:
        logger.exception("generate_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                book.updated_at = datetime.now(timezone.utc)
                session.add(book)
                session.commit()


async def _synthesise_chapter_worker(chapter_id: int, engine) -> bytes:
    from app.models import Book, Chapter
    from app.services.audio.chapter import synthesise_chapter
    from app.services.tts import factory as tts_factory

    settings = get_settings()
    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        book = session.get(Book, chapter.book_id) if chapter else None
        provider = tts_factory.get_tts_provider(
            settings, override=book.tts_provider if book else None
        )
        return await synthesise_chapter(chapter_id, session, provider)


def _generate_chapter_impl(chapter_id: int) -> None:
    from pathlib import Path as _Path

    from app.core.db import get_engine
    from app.core.enums import ChapterStatus
    from app.models import Chapter

    engine = get_engine()

    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        if chapter is None:
            logger.error("generate_chapter called with unknown chapter_id=%d", chapter_id)
            return
        book_id = chapter.book_id
        position = chapter.position
        chapter.status = ChapterStatus.GENERATING
        chapter.error_message = None
        session.add(chapter)
        session.commit()

    try:
        wav_bytes = asyncio.run(_synthesise_chapter_worker(chapter_id, engine))

        out_dir = _Path("data") / str(book_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(out_dir / f"ch{position}.wav")
        _Path(audio_path).write_bytes(wav_bytes)

        with Session(engine) as session:
            chapter = session.get(Chapter, chapter_id)
            chapter.audio_path = audio_path
            chapter.status = ChapterStatus.DONE
            session.add(chapter)
            session.commit()

    except Exception as exc:
        logger.exception("generate_chapter failed for chapter_id=%d", chapter_id)
        with Session(engine) as session:
            chapter = session.get(Chapter, chapter_id)
            if chapter:
                chapter.status = ChapterStatus.FAILED
                chapter.error_message = str(exc)
                session.add(chapter)
                session.commit()


def _process_book_impl(book_id: int) -> None:
    """Chains analyze + generate — preserved for backward compatibility."""
    from app.core.db import get_engine
    from app.core.enums import BookStatus
    from app.models import Book

    _analyze_book_impl(book_id)

    engine = get_engine()
    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None or book.status != BookStatus.ANALYZED:
            return

    _generate_book_impl(book_id)


_VOICE_SAMPLE_TEXT = "Bonjour, voici un aperçu de cette voix clonée par ScriptVox."


async def _generate_voice_sample_async(voice_id: str) -> None:
    """Async variant for FastAPI BackgroundTasks — no Huey worker required."""
    from pathlib import Path

    from app.core.db import get_engine
    from app.core.enums import VoiceKind
    from app.models.entities import Voice

    settings = get_settings()
    if settings.tts_provider != "qwen":
        logger.info("generate_voice_sample_async: skipped (TTS_PROVIDER=%s)", settings.tts_provider)
        return

    engine = get_engine()
    with Session(engine) as session:
        voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
        if voice is None or voice.kind != VoiceKind.CLONED or voice.reference_audio_path is None:
            logger.warning("generate_voice_sample_async: voice %r not found or no ref audio", voice_id)
            return
        ref_path = voice.reference_audio_path

    from app.services.tts.qwen import QwenTTSProvider
    provider = QwenTTSProvider(settings)

    out_dir = Path("data") / "voice_samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"qwen_{voice_id}.wav"

    try:
        wav_bytes = await provider.synthesise(
            _VOICE_SAMPLE_TEXT,
            voice_id,
            reference_audio_path=ref_path,
        )
        out_path.write_bytes(wav_bytes)
        logger.info("generate_voice_sample_async: saved %s", out_path)
    except Exception:
        logger.exception("generate_voice_sample_async failed for voice_id=%r", voice_id)
    finally:
        # Libère le modèle GPU immédiatement après la génération
        import gc
        provider._base_model = None
        provider._model = None
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
            logger.info("generate_voice_sample_async: GPU cache cleared")
        except Exception:
            pass


def _generate_voice_sample_impl(voice_id: str) -> None:
    from pathlib import Path

    from app.core.db import get_engine
    from app.core.enums import VoiceKind
    from app.models.entities import Voice

    settings = get_settings()
    if settings.tts_provider != "qwen":
        logger.info("generate_voice_sample: skipped (TTS_PROVIDER=%s)", settings.tts_provider)
        return

    engine = get_engine()
    with Session(engine) as session:
        voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
        if voice is None or voice.kind != VoiceKind.CLONED or voice.reference_audio_path is None:
            logger.warning("generate_voice_sample: voice %r not found or no ref audio", voice_id)
            return
        ref_path = voice.reference_audio_path

    from app.services.tts.qwen import QwenTTSProvider
    provider = QwenTTSProvider(settings)

    out_dir = Path("data") / "voice_samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"qwen_{voice_id}.wav"

    try:
        wav_bytes = asyncio.run(provider.synthesise(
            _VOICE_SAMPLE_TEXT,
            voice_id,
            reference_audio_path=ref_path,
        ))
        out_path.write_bytes(wav_bytes)
        logger.info("generate_voice_sample: saved %s", out_path)
    except Exception:
        logger.exception("generate_voice_sample failed for voice_id=%r", voice_id)


@huey.task()
def generate_voice_sample(voice_id: str) -> None:
    _generate_voice_sample_impl(voice_id)


@huey.task()
def analyze_book(book_id: int) -> None:
    _analyze_book_impl(book_id)


@huey.task()
def generate_book(book_id: int) -> None:
    _generate_book_impl(book_id)


@huey.task()
def generate_chapter(chapter_id: int) -> None:
    _generate_chapter_impl(chapter_id)


@huey.task()
def process_book(book_id: int) -> None:
    _process_book_impl(book_id)
