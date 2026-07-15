import asyncio
import logging
from pathlib import Path
from typing import Callable

from huey import SqliteHuey
from sqlmodel import Session, select

from app.config import get_settings

logger = logging.getLogger(__name__)

huey = SqliteHuey(filename=get_settings().huey_db_path)
DATA_DIR = Path(get_settings().data_dir)


def _effective_tts_provider(session: Session, book_tts_provider: str | None) -> str | None:
    """Résout le provider TTS effectif : override par livre > préférence globale
    (AppSetting.preferred_tts_provider) > défaut usine (Settings.tts_provider, .env).
    Retourne None si aucun override/préférence n'est défini -- get_tts_provider()
    et assign_voices() retombent alors eux-mêmes sur Settings.tts_provider."""
    from app.models import AppSetting

    if book_tts_provider:
        return book_tts_provider
    row = session.get(AppSetting, 1)
    return row.preferred_tts_provider if row else None


def _effective_book_language(
    parsed_language: str | None, existing_book_language: str | None, session: Session,
) -> str | None:
    """Résout la langue à stocker sur Book.language après un (ré)import EPUB :
    dc:language détecté (parsed_language) > langue déjà connue pour ce livre
    (import précédent ou override manuel via PATCH /books/{id}, jamais écrasée
    par une ré-analyse qui ne détecte rien) > préférence globale
    (AppSetting.preferred_language) en dernier recours. Retourne None si rien
    n'est disponible -- language_profiles.resolve_profile(None) retombe alors
    sur le français, comportement historique inchangé."""
    from app.models import AppSetting

    if parsed_language:
        return parsed_language
    if existing_book_language:
        return existing_book_language
    row = session.get(AppSetting, 1)
    return row.preferred_language if row else None


async def _analyze_book(
    book_id: int,
    chapter_data: list[tuple[int, str]],
    engine,
    resume: bool = False,
    already_done: int = 0,
) -> bool:
    """Returns True if analysis ran to completion, False if aborted (user /stop —
    Book.status flipped to FAILED concurrently). Callers must not proceed to voice
    assignment / ANALYZED on a False return."""
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

    with Session(engine) as session:
        _book = session.get(Book, book_id)
        book_language = _book.language if _book else None

    # Idempotency: wipe any prior LLM results for the chapters we're (re)analyzing.
    # On resume, Characters are preserved (already-known cast from earlier chapters).
    with Session(engine) as session:
        if chapter_ids:
            session.execute(sa_delete(Segment).where(Segment.chapter_id.in_(chapter_ids)))
        if not resume:
            session.execute(sa_delete(Character).where(Character.book_id == book_id))
        session.commit()

    char_map: dict[str, int] = {}  # character name → Character.id (accumulated across chapters)
    if resume:
        with Session(engine) as session:
            existing_chars = session.exec(
                select(Character).where(Character.book_id == book_id)
            ).all()
            char_map = {c.name: c.id for c in existing_chars}

    total = already_done + len(chapter_data)

    for i, (chapter_id, raw_text) in enumerate(chapter_data):
        # Abort if the user triggered /stop while we were processing a previous chapter
        # (or, for i==0, raced in right after PROCESSING was set — checked defensively).
        with Session(engine) as _s:
            _b = _s.get(Book, book_id)
            if _b is None or _b.status == BookStatus.FAILED:
                logger.info("analyze_book: stop requested at chapter %d, aborting", i)
                return False

        known = list(char_map.keys())
        chunks = _chunk_text(raw_text, budget)

        _MAX_RETRIES = 3
        _RETRY_DELAY = 30  # seconds — gives Ollama time to recover from OOM/timeout
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                chunk_results = [
                    await provider.analyze(chunk, known, language=book_language)
                    for chunk in chunks
                ]
                merged = _merge_chunk_results(chunk_results)
                if attempt > 0:
                    logger.info(
                        "analyze_book: book_id=%d chapter %d/%d succeeded on attempt %d",
                        book_id, already_done + i + 1, total, attempt + 1,
                    )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "analyze_book: book_id=%d chapter %d/%d attempt %d/%d failed: %s",
                    book_id, already_done + i + 1, total, attempt + 1, _MAX_RETRIES, exc,
                )
                if attempt < _MAX_RETRIES - 1:
                    with Session(engine) as _s:
                        _b = _s.get(Book, book_id)
                        if _b:
                            _b.error_message = (
                                f"[ch {already_done + i + 1}/{total} essai {attempt + 1}/{_MAX_RETRIES}] "
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
            book.progress = 10.0 + (already_done + i + 1) / total * 50.0
            session.add(book)
            session.commit()

    # Abort if the user triggered /stop after the last chapter finished but before
    # we get to merge suggestions — otherwise this non-essential LLM call would run
    # (and, worse, its caller would then flip the book to ANALYZED regardless).
    with Session(engine) as _s:
        _b = _s.get(Book, book_id)
        if _b is None or _b.status == BookStatus.FAILED:
            logger.info("analyze_book: stop requested before suggest_merges, aborting")
            return False

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

    return True


def _release_qwen_gpu(provider) -> None:
    """Best-effort VRAM release once a synthesis run ends. Only the internal
    Base<->CustomVoice swap (qwen.py `_ensure_model`/`_ensure_base_model`) ever
    cleared CUDA memory before -- a normal generate_book/generate_chapter run
    never did, leaving VRAM reserved by this process for its whole lifetime
    even after switching to a different TTS provider for the next book (risk
    of contention with Ollama, see memory tts_emotion_qwen3_direction). No-op
    for any provider that isn't Qwen, or if nothing was actually loaded during
    this run."""
    from app.services.tts.qwen import QwenTTSProvider
    if not isinstance(provider, QwenTTSProvider):
        return
    if provider._model is None and provider._base_model is None:
        return
    import gc
    provider._model = None
    provider._base_model = None
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def _make_chapter_stop_checker(engine, chapter_id: int) -> Callable[[], bool]:
    """Mirrors _make_book_stop_checker but polls Chapter.cancel_requested — used by
    standalone (non book-driven) chapter generation, which has no Book.status to
    watch. Fresh Session per call, same reasoning as the book checker."""
    from app.models import Chapter

    def _should_abort() -> bool:
        with Session(engine) as s:
            c = s.get(Chapter, chapter_id)
            return c is None or c.cancel_requested

    return _should_abort


def _make_book_stop_checker(engine, book_id: int) -> Callable[[], bool]:
    """Returns a zero-arg callable reporting whether /stop was triggered for this
    book. Opens a FRESH short-lived Session on every call, never reused across
    calls -- reusing a long-lived session would return a stale cached Book row
    from its identity map, missing a concurrent commit made by the /stop route's
    own session (same pattern the per-segment stop-check already relied on,
    Lot A)."""
    from app.core.enums import BookStatus
    from app.models import Book

    def _should_abort() -> bool:
        with Session(engine) as s:
            b = s.get(Book, book_id)
            return b is None or b.status == BookStatus.FAILED

    return _should_abort


async def _generate_chapter_async(
    chapter_id: int, engine, should_abort: Callable[[], bool] | None = None,
) -> bool:
    """Synthesise one chapter's audio end-to-end (status, TTS, per-segment timing,
    WAV on disk). Returns True if the chapter completed (status DONE), False if
    aborted via should_abort() before completion.

    On abort, NOTHING is persisted (no WAV file, no timing) and the chapter is
    reverted to PENDING so it gets fully redone on the next attempt -- chapters are
    the retry/reprise unit (Lot C, audit 2026-07-02), so an interrupted chapter's
    partial work is simply discarded rather than reconciled into a torn WAV file
    with partial timing.

    On a genuine failure the chapter is marked FAILED with its error_message (same
    as before this refactor) and the exception is RE-RAISED so a book-driven caller
    can fail the whole book -- a standalone Huey call swallows it instead, see
    _generate_chapter_impl."""
    from pathlib import Path as _Path

    from app.core.enums import ChapterStatus
    from app.models import Chapter, Segment

    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        if chapter is None:
            logger.error("generate_chapter called with unknown chapter_id=%d", chapter_id)
            return False
        book_id = chapter.book_id
        position = chapter.position
        chapter.status = ChapterStatus.GENERATING
        chapter.error_message = None
        session.add(chapter)
        session.commit()

    try:
        result = await _synthesise_chapter_worker(chapter_id, engine, should_abort=should_abort)
        if result is None:
            logger.info(
                "generate_chapter: aborted mid-chapter (chapter_id=%d), reverting to PENDING",
                chapter_id,
            )
            with Session(engine) as session:
                chapter = session.get(Chapter, chapter_id)
                if chapter:
                    chapter.status = ChapterStatus.PENDING
                    chapter.cancel_requested = False
                    session.add(chapter)
                    session.commit()
            return False

        wav_bytes, timing = result

        out_dir = DATA_DIR / str(book_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(out_dir / f"ch{position}.wav")
        _Path(audio_path).write_bytes(wav_bytes)

        with Session(engine) as session:
            for seg_id, offset_ms, dur_ms in timing:
                seg = session.get(Segment, seg_id)
                if seg:
                    seg.audio_offset_ms = offset_ms
                    seg.duration_ms = dur_ms
                    session.add(seg)

            chapter = session.get(Chapter, chapter_id)
            chapter.audio_path = audio_path
            chapter.status = ChapterStatus.DONE
            session.add(chapter)
            session.commit()
        return True

    except Exception as exc:
        logger.exception("generate_chapter failed for chapter_id=%d", chapter_id)
        with Session(engine) as session:
            chapter = session.get(Chapter, chapter_id)
            if chapter:
                chapter.status = ChapterStatus.FAILED
                chapter.error_message = str(exc)
                session.add(chapter)
                session.commit()
        raise


async def _generate_book_async(book_id: int, engine) -> bool:
    """Iterate the book's chapters, generating whichever aren't already DONE
    (reprise -- _generate_book_impl resets every chapter to PENDING first unless
    this is a resume-after-failure, so this only ever skips something on a true
    resume). Stop-aware at SEGMENT granularity: should_abort() is checked before
    each chapter starts AND threaded down into that chapter's own segment loop
    (_synthesise_segments), so /stop takes effect within one segment's TTS call,
    not after a whole chapter finishes. The interrupted chapter's partial work is
    discarded and reverted to PENDING (see _generate_chapter_async) -- the cost of
    a stop is bounded to redoing at most the one chapter in flight, never the book.

    Returns True if every chapter was attempted (some may have been skipped via
    reprise), False if aborted by /stop. Raises on a genuine chapter failure (a
    real TTSError, not an abort) -- the caller's except block fails the whole book,
    reusing the existing book-level error handling unchanged."""
    from app.core.enums import ChapterStatus
    from app.models import Book, Chapter

    should_abort = _make_book_stop_checker(engine, book_id)

    with Session(engine) as session:
        chapters = session.exec(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
        ).all()
        pending = [(c.id, c.status) for c in chapters]

    total = len(pending)
    if total == 0:
        return True

    done_count = sum(1 for _, status in pending if status == ChapterStatus.DONE)

    for i, (chapter_id, status) in enumerate(pending):
        if should_abort():
            logger.info(
                "generate_book: stop requested before chapter %d/%d, aborting", i + 1, total
            )
            return False
        if status == ChapterStatus.DONE:
            continue  # reprise -- déjà généré (résume-après-échec uniquement)

        completed = await _generate_chapter_async(chapter_id, engine, should_abort=should_abort)
        if not completed:
            return False

        done_count += 1
        with Session(engine) as session:
            book = session.get(Book, book_id)
            book.progress = 60.0 + done_count / total * 30.0
            session.add(book)
            session.commit()

    return True


def _analyze_book_impl(book_id: int, force: bool = False) -> None:
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
        previous_status = book.status
        book.status = BookStatus.PROCESSING
        book.progress = 0.0
        book.error_message = None
        session.add(book)
        session.commit()

    resume_requested = previous_status == BookStatus.FAILED and not force

    try:
        from sqlalchemy import delete as sa_delete
        from app.models import Character, CharacterMergeSuggestion, Segment

        with Session(engine) as session:
            existing_chapters = session.exec(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
            ).all()

        do_resume = resume_requested and bool(existing_chapters)

        if do_resume:
            # ── Reprise : pas de re-parse EPUB, on saute les chapitres déjà analysés ──
            with Session(engine) as session:
                chapter_data = []
                for ch in existing_chapters:
                    has_segment = session.exec(
                        select(Segment.id).where(Segment.chapter_id == ch.id).limit(1)
                    ).first()
                    if has_segment is None:
                        chapter_data.append((ch.id, ch.raw_text))
            already_done = len(existing_chapters) - len(chapter_data)
            logger.info(
                "analyze_book: resuming book_id=%d — %d/%d chapters remaining",
                book_id, len(chapter_data), len(existing_chapters),
            )
            with Session(engine) as session:
                book = session.get(Book, book_id)
                book.progress = 10.0
                session.add(book)
                session.commit()
        else:
            # ── Nettoyage idempotent + ré-ingestion EPUB (1er run ou ré-analyse forcée) ──
            with Session(engine) as session:
                existing_ids = [ch.id for ch in existing_chapters]
                if existing_ids:
                    session.execute(sa_delete(Segment).where(Segment.chapter_id.in_(existing_ids)))
                    session.execute(sa_delete(Chapter).where(Chapter.book_id == book_id))
                session.execute(sa_delete(CharacterMergeSuggestion).where(CharacterMergeSuggestion.book_id == book_id))
                session.execute(sa_delete(Character).where(Character.book_id == book_id))
                session.commit()

            # ── EPUB ingestion ─────────────────────────────────────────────────
            parsed = EpubParser().parse(source_path)

            with Session(engine) as session:
                from pathlib import Path as _Path
                book = session.get(Book, book_id)
                book.title = parsed.title
                if parsed.author:
                    book.author = parsed.author
                book.language = _effective_book_language(parsed.language, book.language, session)
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
                    cover_dir = DATA_DIR / str(book_id)
                    cover_dir.mkdir(parents=True, exist_ok=True)
                    cover_file = cover_dir / f"cover{ext}"
                    cover_file.write_bytes(parsed.cover_image)
                    book.cover_path = str(cover_file)
                book.progress = 10.0
                session.add(book)
                session.commit()
                chapters = session.exec(
                    select(Chapter)
                    .where(Chapter.book_id == book_id)
                    .order_by(Chapter.position)
                ).all()
                chapter_data = [(ch.id, ch.raw_text) for ch in chapters]
            already_done = 0

        # ── LLM analysis (progress 10% → 60%) ─────────────────────────────────
        completed = asyncio.run(_analyze_book(
            book_id, chapter_data, engine, resume=do_resume, already_done=already_done,
        ))
        if not completed:
            # Aborted by a concurrent /stop — Book.status is already FAILED (set by
            # the stop endpoint). Never proceed to voice assignment / ANALYZED.
            logger.info("analyze_book: aborted by stop for book_id=%d", book_id)
            return

        # ── Voice assignment ───────────────────────────────────────────────────
        # Use the book's own TTS provider override when set, falling back to the
        # global default otherwise — mirrors tts_factory.get_tts_provider's own
        # override resolution (tasks.py _synthesise_book/_synthesise_chapter_worker).
        # Passing the global unconditionally (previous behaviour) meant a book
        # overridden to qwen never got clone-priority when the global wasn't qwen,
        # and a book overridden AWAY from qwen still got clones assigned when the
        # global was qwen -- voices that then fail to resolve at synthesis time
        # (audit 2026-07-02, finding M4).
        with Session(engine) as session:
            book = session.get(Book, book_id)
            effective_tts_provider = _effective_tts_provider(
                session, book.tts_provider if book else None,
            ) or get_settings().tts_provider
            assign_voices(book_id, session, tts_provider=effective_tts_provider)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            # Re-check: a /stop could have raced in between the check above and here.
            # Never overwrite a FAILED status with ANALYZED.
            if book is not None and book.status != BookStatus.FAILED:
                book.status = BookStatus.ANALYZED
                book.progress = 100.0
                session.add(book)
                session.commit()

    except Exception as exc:
        logger.exception("analyze_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                session.add(book)
                session.commit()


def _generate_book_impl(book_id: int) -> None:
    from app.core.db import get_engine
    from app.core.enums import BookStatus, ChapterStatus
    from app.models import Book, Chapter
    from app.services.audio.assembler import assemble_wav_from_files, wav_to_mp3_streaming

    engine = get_engine()

    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None:
            logger.error("generate_book called with unknown book_id=%d", book_id)
            return
        if book.status not in (BookStatus.ANALYZED, BookStatus.DONE, BookStatus.FAILED):
            logger.warning(
                "generate_book skipped: book_id=%d has status=%s", book_id, book.status
            )
            return
        source_path = book.source_path
        previous_status = book.status
        book.status = BookStatus.GENERATING
        book.progress = 0.0
        book.error_message = None
        session.add(book)
        session.commit()

    # Reprise (skip chapters already DONE) only applies when resuming after a
    # failure — a fresh "Générer"/"Regénérer" click on ANALYZED/DONE must redo
    # everything, so every chapter is reset to PENDING first (mirrors
    # _analyze_book_impl's resume_requested/force pattern; audit 2026-07-02 Lot C).
    resume = previous_status == BookStatus.FAILED
    if not resume:
        with Session(engine) as session:
            chapters = session.exec(select(Chapter).where(Chapter.book_id == book_id)).all()
            for c in chapters:
                if c.status != ChapterStatus.DONE:
                    continue
                c.status = ChapterStatus.PENDING
                c.audio_path = None
                session.add(c)
            session.commit()

    try:
        # ── TTS synthesis, chapter by chapter (progress 60% → 90%) ────────────
        completed = asyncio.run(_generate_book_async(book_id, engine))
        if not completed:
            # Aborted by a concurrent /stop — Book.status is already FAILED (set by
            # the stop endpoint). Never proceed to assembling / writing DONE.
            logger.info("generate_book: aborted by stop for book_id=%d", book_id)
            return

        # ── Assemble the book WAV from the per-chapter WAVs already on disk ────
        # (streamed disk-to-disk, one chapter's frames in memory at a time — not
        # the whole book, unlike the old flat-segment-loop design it replaces).
        with Session(engine) as session:
            done_chapters = session.exec(
                select(Chapter)
                .where(Chapter.book_id == book_id, Chapter.status == ChapterStatus.DONE)
                .order_by(Chapter.position)
            ).all()
            chapter_wav_paths = [c.audio_path for c in done_chapters if c.audio_path]

        audio_path: str | None = None
        mp3_path: str | None = None
        if chapter_wav_paths:
            from pathlib import Path as _Path
            audio_path = str(_Path(source_path).with_suffix(".wav"))
            assemble_wav_from_files(chapter_wav_paths, audio_path)
            # Both steps are now disk-to-disk, streamed in bounded chunks (Lot C2,
            # audit 2026-07-02): assembling the book WAV from per-chapter WAVs
            # above, and encoding it to MP3 here — neither holds more than one
            # chapter's / one chunk's worth of PCM in memory at a time, instead of
            # the whole book (~1.6 GB of PCM for a 10-hour novel).
            mp3_file = _Path(audio_path).with_suffix(".mp3")
            wav_to_mp3_streaming(audio_path, mp3_file)
            mp3_path = str(mp3_file)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            # Re-check: a /stop could have raced in between the last chapter and
            # here. Never overwrite a FAILED status with DONE.
            if book is None or book.status == BookStatus.FAILED:
                logger.info("generate_book: stop requested just before commit, aborting")
                return
            book.audio_path = audio_path
            book.mp3_path = mp3_path
            book.status = BookStatus.DONE
            book.progress = 100.0
            session.add(book)
            session.commit()

    except Exception as exc:
        logger.exception("generate_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                session.add(book)
                session.commit()


async def _synthesise_chapter_worker(
    chapter_id: int, engine, should_abort: Callable[[], bool] | None = None,
) -> tuple[bytes, list[tuple[int, int, int]]] | None:
    """Returns (wav_bytes, [(seg_id, offset_ms, duration_ms)]), or None if
    should_abort() fired before the chapter finished synthesising."""
    from app.models import Book, Chapter
    from app.services.audio.chapter import _synthesise_segments
    from app.services.tts import factory as tts_factory

    settings = get_settings()
    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        book = session.get(Book, chapter.book_id) if chapter else None
        provider = tts_factory.get_tts_provider(
            settings,
            override=_effective_tts_provider(session, book.tts_provider if book else None),
            language=book.language if book else None,
        )
        try:
            return await _synthesise_segments(
                chapter_id, session, provider, should_abort=should_abort,
            )
        finally:
            _release_qwen_gpu(provider)


def _generate_chapter_impl(chapter_id: int) -> None:
    """Huey-facing entry point for a standalone (non book-driven) chapter
    generation. Stop-aware via Chapter.cancel_requested (polled between segments,
    see _make_chapter_stop_checker) — set by POST /books/{id}/chapters/{pos}/stop.
    Swallows the exception _generate_chapter_async already turned into
    Chapter.FAILED, matching the pre-existing contract of never letting an
    exception propagate out of a Huey task."""
    from app.core.db import get_engine

    engine = get_engine()
    should_abort = _make_chapter_stop_checker(engine, chapter_id)
    try:
        asyncio.run(_generate_chapter_async(chapter_id, engine, should_abort=should_abort))
    except Exception:
        pass  # already persisted to Chapter.FAILED inside _generate_chapter_async


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


def _generate_voice_sample_impl(voice_id: str) -> None:
    """Runs exclusively in the Huey worker process (audit 2026-07-02, Lot F1 /
    M5): loading a Qwen checkpoint and holding CUDA state used to happen inline
    in the FastAPI process on every POST /voices/{id}/sample, risking VRAM
    contention with a book/chapter generation running in the worker at the same
    time — two separate processes touching the same GPU with no coordination."""
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

    out_dir = DATA_DIR / "voice_samples"
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
    finally:
        _release_qwen_gpu(provider)


@huey.task()
def generate_voice_sample(voice_id: str) -> None:
    _generate_voice_sample_impl(voice_id)


@huey.task()
def analyze_book(book_id: int, force: bool = False) -> None:
    _analyze_book_impl(book_id, force)


@huey.task()
def generate_book(book_id: int) -> None:
    _generate_book_impl(book_id)


@huey.task()
def generate_chapter(chapter_id: int) -> None:
    _generate_chapter_impl(chapter_id)


async def _generate_segment_async(take_id: int, engine) -> None:
    """Synthesise one SegmentTake: TTS → WAV on disk → take.audio_path updated."""
    from pathlib import Path as _Path

    from sqlmodel import select as _select

    from app.models.entities import SegmentTake, Voice
    from app.models import Book, Chapter, Segment
    from app.services.audio.chapter import _synthesise_with_retry
    from app.services.tts import factory as tts_factory

    settings = get_settings()

    with Session(engine) as session:
        take = session.get(SegmentTake, take_id)
        if take is None:
            logger.error("generate_segment: unknown take_id=%d", take_id)
            return
        segment = session.get(Segment, take.segment_id)
        if segment is None:
            logger.error("generate_segment: segment missing for take_id=%d", take_id)
            return
        chapter = session.get(Chapter, segment.chapter_id)
        if chapter is None:
            logger.error("generate_segment: chapter missing for take_id=%d", take_id)
            return
        book = session.get(Book, chapter.book_id)

        voice_id = take.voice_id
        emotion = take.emotion
        seg_text = segment.text
        book_id = chapter.book_id

        v = session.exec(_select(Voice).where(Voice.voice_id == voice_id)).first()
        ref_path = v.reference_audio_path if v else None

        provider = tts_factory.get_tts_provider(
            settings,
            override=_effective_tts_provider(session, book.tts_provider if book else None),
            language=book.language if book else None,
        )

    try:
        wav_bytes = await _synthesise_with_retry(
            provider, seg_text, voice_id,
            emotion=emotion, reference_audio_path=ref_path,
        )
    finally:
        _release_qwen_gpu(provider)

    takes_dir = DATA_DIR / str(book_id) / "takes"
    takes_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(takes_dir / f"{take_id}.wav")
    _Path(audio_path).write_bytes(wav_bytes)

    with Session(engine) as session:
        take = session.get(SegmentTake, take_id)
        if take:
            take.audio_path = audio_path
            session.add(take)
            session.commit()


def _generate_segment_impl(take_id: int) -> None:
    from app.core.db import get_engine
    engine = get_engine()
    asyncio.run(_generate_segment_async(take_id, engine))


@huey.task()
def generate_segment(take_id: int) -> None:
    _generate_segment_impl(take_id)


@huey.task()
def process_book(book_id: int) -> None:
    _process_book_impl(book_id)
