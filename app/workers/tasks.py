import asyncio
import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from huey import SqliteHuey, crontab
from sqlmodel import Session, select

from app.config import get_settings

logger = logging.getLogger(__name__)

huey = SqliteHuey(filename=get_settings().huey_db_path)
DATA_DIR = Path(get_settings().data_dir)


def _parse_options(raw: str | None) -> dict:
    """AppSetting.llm_options / tts_options : JSON d'un dict de réglages à chaud (model,
    base_url…). Toute valeur invalide donne {} (jamais d'exception dans le worker)."""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _llm_options(session: Session) -> dict:
    from app.models import AppSetting

    row = session.get(AppSetting, 1)
    return _parse_options(row.llm_options) if row else {}


def _tts_options(session: Session) -> dict:
    from app.models import AppSetting

    row = session.get(AppSetting, 1)
    return _parse_options(row.tts_options) if row else {}


# ── Cache des providers TTS « à modèle lourd » (BE-1, audit 2026-09-25) ─────────
# Un provider qui déclare keep_loaded=True (Qwen3-TTS…) reste instancié — donc son modèle
# chargé en VRAM — d'un chapitre à l'autre et d'une régénération de réplique à l'autre.
# Avant : rechargé (≈ 3-4 Go, dizaines de secondes) à CHAQUE chapitre. Déchargé sur demande
# (release_qwen_vram), après TTS_IDLE_UNLOAD_SECONDS d'inactivité, ou avant une analyse LLM.
# Process worker uniquement : l'API ne charge jamais de modèle (voir voices.py).
_TTS_CACHE: dict[str, object] = {}
_TTS_LAST_USED = 0.0
_TTS_CACHE_LOCK = threading.Lock()


def _get_tts_provider(settings, session: Session, book):
    """Provider TTS effectif d'un livre (override livre > préférence Paramètres > .env),
    avec les réglages à chaud de Paramètres ; réutilisé depuis le cache s'il garde son modèle
    chargé."""
    global _TTS_LAST_USED
    from app.services.tts import factory as tts_factory

    override = _effective_tts_provider(session, book.tts_provider if book else None)
    language = book.language if book else None
    options = _tts_options(session)
    kwargs: dict = {"override": override, "language": language}
    if options:
        kwargs["options"] = options
    key = json.dumps([override or settings.tts_provider, language, options], sort_keys=True)
    with _TTS_CACHE_LOCK:
        cached = _TTS_CACHE.get(key)
        if cached is not None:
            _TTS_LAST_USED = time.monotonic()
            return cached
    provider = tts_factory.get_tts_provider(settings, **kwargs)
    if getattr(provider, "keep_loaded", False) is True:
        with _TTS_CACHE_LOCK:
            _TTS_CACHE[key] = provider
            _TTS_LAST_USED = time.monotonic()
    return provider


def _release_all_tts() -> int:
    """Décharge tous les modèles TTS gardés en mémoire. Retourne le nombre déchargé."""
    with _TTS_CACHE_LOCK:
        providers = list(_TTS_CACHE.values())
        _TTS_CACHE.clear()
    for provider in providers:
        try:
            provider.unload()
        except Exception:  # noqa: BLE001
            logger.warning("tts unload failed", exc_info=True)
    return len(providers)


def _touch_tts() -> None:
    global _TTS_LAST_USED
    _TTS_LAST_USED = time.monotonic()


# ── Débit mesuré -> temps restant (BE-5) ────────────────────────────────────────
# (caractères traités, secondes) des derniers éléments par livre et par étape ; moyenne
# glissante sur 8 mesures. En mémoire : perdu au redémarrage du worker (ETA None le temps
# de refaire 1-2 mesures), sans conséquence.
_THROUGHPUT: dict[tuple[int, str], list[tuple[int, float]]] = {}


def _record_throughput(book_id: int, stage: str, chars: int, seconds: float) -> None:
    samples = _THROUGHPUT.setdefault((book_id, stage), [])
    if chars > 0 and seconds > 0:
        samples.append((chars, seconds))
        del samples[:-8]


def _eta_seconds(book_id: int, stage: str, remaining_chars: int) -> int | None:
    samples = _THROUGHPUT.get((book_id, stage)) or []
    total_chars = sum(c for c, _ in samples)
    total_secs = sum(t for _, t in samples)
    if not samples or total_chars <= 0 or total_secs <= 0 or remaining_chars <= 0:
        return None
    return int(remaining_chars / (total_chars / total_secs))


def _effective_llm_provider(session: Session) -> str | None:
    """Résout le provider LLM effectif : préférence globale
    (AppSetting.preferred_llm_provider) > défaut usine (Settings.llm_provider, .env).
    Retourne None si aucune préférence n'est définie -- get_llm_provider()
    retombe alors sur Settings.llm_provider."""
    from app.models import AppSetting

    row = session.get(AppSetting, 1)
    return row.preferred_llm_provider if row else None


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

    from app.core.enums import BookStatus, MergeSuggestionStatus
    from app.models import Book, Character, CharacterMergeSuggestion, Segment
    from app.services.llm.base import (
        GEMINI_MAX_TOKENS,
        CharacterData,
        _chunk_text,
        _merge_chunk_results,
    )
    from app.services.llm import factory as llm_factory

    settings = get_settings()
    with Session(engine) as _s:
        llm_override = _effective_llm_provider(_s)
        llm_opts = _llm_options(_s)
    # `options` (réglages à chaud de Paramètres) n'est passé que s'il y en a : les anciens
    # points d'injection (tests, plugins sans options) restent appelables tels quels.
    llm_kwargs: dict = {"override": llm_override}
    if llm_opts:
        llm_kwargs["options"] = llm_opts
    provider = llm_factory.get_llm_provider(settings, **llm_kwargs)
    effective_llm = llm_override or settings.llm_provider
    provider_budget = getattr(provider, "chunk_tokens", None)
    if isinstance(provider_budget, int) and not isinstance(provider_budget, bool) and provider_budget > 0:
        budget = provider_budget
    else:
        budget = (
            settings.ollama_chunk_tokens
            if effective_llm == "ollama"
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

    remaining_chars = sum(len(t) for _, t in chapter_data)
    for i, (chapter_id, raw_text) in enumerate(chapter_data):
        _chapter_started = time.monotonic()
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
                    # Nettoie le message de retry laissé par la tentative ratée
                    # ("[ch X/Y essai Z/3] ... nouvel essai dans 30s") -- jamais
                    # effacé jusqu'ici si la tentative suivante réussissait, le
                    # livre finissait ANALYZED avec un message de progression
                    # périmé exposé par l'API (audit 2026-07-11). Gardé derrière
                    # `status != FAILED` : un /stop a pu survenir PENDANT le
                    # sleep entre deux tentatives (la boucle ne le revérifie pas
                    # avant de retenter) -- ne jamais écraser l'arrêt utilisateur
                    # légitime qui a déjà positionné error_message avant nous.
                    with Session(engine) as _s:
                        _b = _s.get(Book, book_id)
                        if _b and _b.status != BookStatus.FAILED:
                            _b.error_message = None
                            _s.add(_b)
                            _s.commit()
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

            _record_throughput(
                book_id, "analysis", len(raw_text), time.monotonic() - _chapter_started,
            )
            remaining_chars -= len(raw_text)
            book = session.get(Book, book_id)
            book.progress = 10.0 + (already_done + i + 1) / total * 50.0
            book.stage = "analysis"
            book.stage_progress = (already_done + i + 1) / total * 100.0
            book.eta_seconds = _eta_seconds(book_id, "analysis", remaining_chars)
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

        # Purge les suggestions PENDING existantes avant d'insérer les
        # nouvelles (audit 2026-07-11) : ce bloc tourne aussi lors d'une
        # reprise d'analyse, sans jamais avoir purgé les suggestions d'un
        # passage précédent (la purge de CharacterMergeSuggestion n'existe que
        # dans la branche non-resume de _analyze_book_impl) -- doublons PENDING
        # accumulés à chaque reprise. Purgée même si `suggestions` est vide :
        # une reprise qui ne retrouve plus de doublon (casting changé entre
        # temps) ne doit pas laisser une suggestion PENDING périmée.
        with Session(engine) as session:
            session.execute(
                sa_delete(CharacterMergeSuggestion).where(
                    CharacterMergeSuggestion.book_id == book_id,
                    CharacterMergeSuggestion.status == MergeSuggestionStatus.PENDING,
                )
            )
            session.commit()

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

    # Libère la VRAM du LLM local (LLM-4) : la synthèse vocale locale en a besoin, et sur une
    # carte de 16 Go un LLM de 13-17 Go + Qwen3-TTS ne tiennent pas ensemble.
    if settings.llm_unload_after_analysis is True:
        try:
            unload = getattr(provider, "unload", None)
            if callable(unload):
                unload()
        except Exception:  # noqa: BLE001 — best-effort
            logger.warning("llm unload failed", exc_info=True)

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


def _extract_wav_slice(wav_bytes: bytes, offset_ms: int, dur_ms: int) -> bytes:
    """Extract a time window from assembled WAV bytes and return it as a standalone WAV."""
    import io as _io, wave as _wave
    with _wave.open(_io.BytesIO(wav_bytes), "rb") as src:
        ch, sw, fr = src.getnchannels(), src.getsampwidth(), src.getframerate()
        src.setpos(int(offset_ms * fr / 1000))
        pcm = src.readframes(int(dur_ms * fr / 1000))
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as dst:
        dst.setnchannels(ch)
        dst.setsampwidth(sw)
        dst.setframerate(fr)
        dst.writeframes(pcm)
    return buf.getvalue()


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


def _make_chapter_or_book_stop_checker(
    engine, book_id: int, chapter_id: int,
) -> Callable[[], bool]:
    """OR of the book-level and chapter-level stop checkers — used by book-driven
    generation (_generate_book_async) so that stopping the ONE chapter currently
    being synthesised (POST /books/{id}/chapters/{n}/stop, Chapter.cancel_requested)
    takes effect immediately, not just Book.status (audit 2026-07-11: before this,
    a per-chapter stop clicked during a whole-book run had no effect at all — the
    chapter just finished normally, and the residual flag silently aborted the
    NEXT unrelated standalone dispatch of that same chapter instead)."""
    book_check = _make_book_stop_checker(engine, book_id)
    chapter_check = _make_chapter_stop_checker(engine, chapter_id)

    def _should_abort() -> bool:
        return book_check() or chapter_check()

    return _should_abort


async def _generate_chapter_async(
    chapter_id: int, engine, should_abort: Callable[[], bool] | None = None,
) -> bool:
    """Synthesise one chapter's audio end-to-end (status, TTS, per-segment timing,
    WAV on disk). Returns True if the chapter completed (status DONE), False if
    aborted via should_abort() before completion.

    On abort, no chapter-level result is persisted (no WAV file, no timing) and the
    chapter is reverted to PENDING -- never a torn WAV with partial timing. The
    segments already synthesised DO survive, in the per-segment cache
    (segment_cache_dir): the next attempt re-reads them instead of paying their TTS
    again, and only the missing segments are synthesised (reprise par segment).

    On a genuine failure the chapter is marked FAILED with its error_message (same
    as before this refactor) and the exception is RE-RAISED so a book-driven caller
    can fail the whole book -- a standalone Huey call swallows it instead, see
    _generate_chapter_impl."""
    from pathlib import Path as _Path

    from app.core.enums import ChapterStatus
    from app.models import Chapter, Segment

    _t_started = time.monotonic()
    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        if chapter is None:
            logger.error("generate_chapter called with unknown chapter_id=%d", chapter_id)
            return False
        book_id = chapter.book_id
        position = chapter.position
        chapter.status = ChapterStatus.GENERATING
        chapter.error_message = None
        # Nettoie un cancel_requested résiduel d'un cycle précédent (audit
        # 2026-07-11) : un /stop cliqué juste après le DERNIER segment arrive
        # trop tard pour être revérifié -- le chapitre finit DONE avec le flag
        # toujours à True (seul le chemin d'abandon le remet à False). Sans ce
        # reset, la PROCHAINE tentative de ce chapitre avorterait à vide dès
        # son premier segment, avant même de vraiment démarrer.
        chapter.cancel_requested = False
        # Sort de la file immédiatement -- la pompe (generate_chapter_queue_pump)
        # ne doit plus jamais reconsidérer ce chapitre une fois pris en charge,
        # que la synthèse aboutisse, échoue ou soit abandonnée (audit
        # 2026-07-11, Lot 3).
        chapter.queued_at = None
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
        # Mastering ACX du chapitre ENTIER (même durée : le minutage des segments reste
        # valable) avant l'écriture et le découpage en prises.
        if getattr(get_settings(), "audio_mastering", "acx") == "acx":
            from app.services.audio.mastering import master
            wav_bytes = master(wav_bytes)

        out_dir = DATA_DIR / str(book_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(out_dir / f"ch{position}.wav")
        _Path(audio_path).write_bytes(wav_bytes)

        with Session(engine) as session:
            from sqlalchemy import delete as _sa_delete
            from app.core.enums import SegmentType as _SegType
            from app.models.entities import Character as _Char, SegmentTake as _STake
            from app.services.voice_assignment import NARRATOR_VOICE_ID as _NARRATOR

            seg_ids = [sid for sid, _, _ in timing]
            if seg_ids:
                session.execute(_sa_delete(_STake).where(_STake.segment_id.in_(seg_ids)))
            session.flush()

            seg_voice: list[tuple[int, int, int, str]] = []
            for seg_id, offset_ms, dur_ms in timing:
                seg = session.get(Segment, seg_id)
                if seg:
                    seg.audio_offset_ms = offset_ms
                    seg.duration_ms = dur_ms
                    session.add(seg)
                    if seg.segment_type == _SegType.NARRATION or seg.character_id is None:
                        vid = _NARRATOR
                    else:
                        char = session.get(_Char, seg.character_id)
                        vid = char.voice_id if char and char.voice_id else _NARRATOR
                    seg_voice.append((seg_id, offset_ms, dur_ms, vid))

            chapter = session.get(Chapter, chapter_id)
            chapter.audio_path = audio_path
            chapter.status = ChapterStatus.DONE
            if timing:
                _last = timing[-1]
                chapter.duration_ms = _last[1] + _last[2]
            _chars_done = len(chapter.raw_text or "")
            session.add(chapter)

            takes_dir = DATA_DIR / str(book_id) / "takes"
            takes_dir.mkdir(parents=True, exist_ok=True)
            take_info: list[tuple] = []
            for seg_id, offset_ms, dur_ms, vid in seg_voice:
                take = _STake(segment_id=seg_id, voice_id=vid, is_selected=True)
                session.add(take)
                take_info.append((take, offset_ms, dur_ms))
            session.flush()

            for take, offset_ms, dur_ms in take_info:
                wav_slice = _extract_wav_slice(wav_bytes, offset_ms, dur_ms)
                take_path = str(takes_dir / f"{take.id}.wav")
                _Path(take_path).write_bytes(wav_slice)
                take.audio_path = take_path
                session.add(take)

            session.commit()
        # Chapitre complet : le cache de reprise par segment n'a plus d'usage, et une
        # régénération volontaire doit repartir de zéro (nouvelle prise).
        shutil.rmtree(segment_cache_dir(book_id, chapter_id), ignore_errors=True)
        _record_throughput(book_id, "generation", _chars_done, time.monotonic() - _t_started)
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
    from app.core.enums import BookStatus, ChapterStatus
    from app.models import Book, Chapter

    should_abort = _make_book_stop_checker(engine, book_id)

    with Session(engine) as session:
        chapters = session.exec(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
        ).all()
        pending = [(c.id, c.status) for c in chapters]

    total = len(pending)
    if total == 0:
        # Defense in depth (audit 2026-07-11): the API route already rejects
        # this with a 409 before ever dispatching generate_book, but treating
        # an empty chapter list as trivially "complete" here let ANY caller
        # (e.g. the legacy process_book chain, or a future one) mark a book
        # DONE/progress=100 with audio_path=None — a book that lies about
        # being finished. A book with zero chapters never finished analysis;
        # that is a failure, not a no-op success.
        raise ValueError(f"Book {book_id} has no chapters — analysis never completed")

    done_count = sum(1 for _, status in pending if status == ChapterStatus.DONE)

    for i, (chapter_id, status) in enumerate(pending):
        if should_abort():
            logger.info(
                "generate_book: stop requested before chapter %d/%d, aborting", i + 1, total
            )
            return False
        if status == ChapterStatus.DONE:
            continue  # reprise -- déjà généré (résume-après-échec uniquement)

        # Combine le checker livre avec celui de CE chapitre : Chapter.cancel_requested
        # posé par POST /books/{id}/chapters/{n}/stop sur le chapitre en cours de
        # synthèse pendant une génération pilotée par le livre était jusqu'ici
        # invisible ici (should_abort ne surveillait que Book.status) -- le flag
        # ne prenait effet que lors d'une future tentative standalone de ce même
        # chapitre (audit 2026-07-11).
        chapter_abort = _make_chapter_or_book_stop_checker(engine, book_id, chapter_id)
        completed = await _generate_chapter_async(chapter_id, engine, should_abort=chapter_abort)
        if not completed:
            # L'abandon peut venir du flag de CE chapitre plutôt que de
            # Book.status (déjà FAILED par la route /stop niveau livre) -- si
            # c'est le cas, Book.status est encore GENERATING ici et doit être
            # basculé nous-mêmes, sinon le livre reste bloqué GENERATING pour
            # toujours (aucun code ne le fait jamais avancer autrement).
            with Session(engine) as session:
                book = session.get(Book, book_id)
                if book is not None and book.status == BookStatus.GENERATING:
                    book.status = BookStatus.FAILED
                    book.error_message = "Arrêté par l'utilisateur."
                    book.failed_stage = "generation"
                    session.add(book)
                    session.commit()
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
        book.stage = "analysis"
        book.stage_progress = 0.0
        book.eta_seconds = None
        book.error_message = None
        book.failed_stage = None  # nettoie une valeur périmée d'une tentative précédente
        session.add(book)
        session.commit()

    # Les modèles TTS gardés en mémoire (BE-1) n'ont rien à faire en VRAM pendant une analyse.
    _release_all_tts()

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
                    if not ch.included:
                        continue
                    has_segment = session.exec(
                        select(Segment.id).where(Segment.chapter_id == ch.id).limit(1)
                    ).first()
                    if has_segment is None:
                        chapter_data.append((ch.id, ch.raw_text))
            already_done = sum(1 for c in existing_chapters if c.included) - len(chapter_data)
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
                        included=getattr(pc, "included", True),
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
                chapter_data = [(ch.id, ch.raw_text) for ch in chapters if ch.included]
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
                book.stage = None
                book.stage_progress = 0.0
                book.eta_seconds = None
                session.add(book)
                session.commit()

    except Exception as exc:
        logger.exception("analyze_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                book.failed_stage = "analysis"
                book.stage = None
                book.eta_seconds = None
                session.add(book)
                session.commit()


def _assemble_book(engine, book_id: int, source_path: str) -> tuple[str | None, str | None, str | None]:
    """Assemble le livre complet à partir des WAV de chapitres déjà sur disque : WAV, MP3 et
    (si ffmpeg est disponible) M4B chapitré avec couverture. Tout se fait disque à disque, par
    blocs bornés (mémoire constante, audit 2026-07-02 C1/C2). Retourne (wav, mp3, m4b) ;
    (None, None, None) si aucun chapitre n'a d'audio.

    Les chapitres sont séparés par un silence (AUDIO_PAUSE_CHAPTER_MS) ; un chapitre généré
    à une autre fréquence (avant le passage à 24 kHz) est converti à la volée."""
    from pathlib import Path as _Path

    from app.core.enums import ChapterStatus
    from app.models import Book, Chapter
    from app.services.audio import m4b as m4b_mod
    from app.services.audio.assembler import assemble_wav_from_files, wav_to_mp3_streaming
    from app.services.audio.format import OUTPUT_SAMPLE_RATE

    settings = get_settings()
    with Session(engine) as session:
        done_chapters = session.exec(
            select(Chapter)
            .where(Chapter.book_id == book_id, Chapter.status == ChapterStatus.DONE)
            .order_by(Chapter.position)
        ).all()
        chapters = [(c.position, c.title, c.audio_path) for c in done_chapters
                    if c.audio_path and c.included]
        book = session.get(Book, book_id)
        book_title = book.title if book else "Livre"
        book_author = book.author if book else None
        cover_path = book.cover_path if book else None
        book_year = book.published_at.year if book and book.published_at else None
        book_genre = book.genre if book else None
        engine_name = _effective_tts_provider(session, book.tts_provider if book else None)             or settings.tts_provider
    if not chapters:
        return None, None, None

    gap = settings.pause_chapter_ms if isinstance(settings.pause_chapter_ms, int) else 0
    paths = [c[2] for c in chapters]
    audio_path = str(_Path(source_path).with_suffix(".wav"))
    assemble_wav_from_files(paths, audio_path, target_rate=OUTPUT_SAMPLE_RATE, gaps_ms=gap)
    mp3_file = _Path(audio_path).with_suffix(".mp3")
    wav_to_mp3_streaming(audio_path, mp3_file)

    durations = [m4b_mod.wav_file_duration_ms(p) for p in paths]
    titles = [c[1] or f"Chapitre {c[0]}" for c in chapters]
    marks = m4b_mod.chapter_marks(durations, titles, gap)
    # Horodatage des chapitres (.txt), écrit même sans ffmpeg.
    m4b_mod.chapters_txt_path(audio_path).write_text(
        m4b_mod.chapters_txt(marks), encoding="utf-8", newline="\n",
    )

    m4b_path: str | None = None
    ffmpeg = m4b_mod.find_ffmpeg(getattr(settings, "ffmpeg_path", None)
                                 if isinstance(getattr(settings, "ffmpeg_path", None), str) else None)
    if ffmpeg:
        built = m4b_mod.build_m4b(
            audio_path, _Path(audio_path).with_suffix(".m4b"), title=book_title,
            author=book_author, chapters=marks, cover_path=cover_path, ffmpeg=ffmpeg,
            year=book_year, genre=book_genre, narrator=f"Voix de synthèse ({engine_name})",
            comment="Livre audio produit avec ScriptVox",
        )
        m4b_path = str(built) if built else None
    return audio_path, str(mp3_file), m4b_path


def _update_generation_progress(session: Session, book, chapters) -> None:
    """Progression de l'étape « génération » : pondérée par la taille du texte (un chapitre
    de 30 pages pèse plus qu'un de 2), avec temps restant estimé (BE-5)."""
    from app.core.enums import ChapterStatus

    included = [c for c in chapters if c.included]
    total_chars = sum(len(c.raw_text or "") for c in included) or 1
    done_chars = sum(len(c.raw_text or "") for c in included if c.status == ChapterStatus.DONE)
    remaining = total_chars - done_chars
    book.stage = "generation"
    book.stage_progress = min(100.0, done_chars / total_chars * 100.0)
    book.progress = 60.0 + done_chars / total_chars * 30.0
    book.eta_seconds = _eta_seconds(book.id, "generation", remaining)
    session.add(book)


def _advance_books(engine) -> None:
    """Fait avancer les livres en cours de génération par la file de chapitres (BE-3).

    Appelé après chaque chapitre traité par la pompe. Pour chaque livre GENERATING :
      - des chapitres encore en file ou en cours -> met à jour progression et temps restant ;
      - un chapitre FAILED -> le livre passe FAILED (reprise possible, chapitres DONE conservés) ;
      - un chapitre ni fait ni en file (arrêté à la main) -> livre FAILED « Arrêté » ;
      - tout est DONE -> assemble WAV/MP3/M4B puis livre DONE.
    Un livre déjà FAILED (bouton Arrêter du livre) n'est jamais réécrit.
    """
    from app.core.enums import BookStatus, ChapterStatus
    from app.models import Book, Chapter

    with Session(engine) as session:
        book_ids = [b.id for b in session.exec(
            select(Book).where(Book.status == BookStatus.GENERATING)
        ).all()]

    for book_id in book_ids:
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book is None or book.status != BookStatus.GENERATING:
                continue
            chapters = session.exec(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
            ).all()
            included = [c for c in chapters if c.included]
            in_flight = [c for c in included if c.status == ChapterStatus.GENERATING
                         or (c.status == ChapterStatus.PENDING and c.queued_at is not None)]
            failed = [c for c in included if c.status == ChapterStatus.FAILED]
            if in_flight:
                _update_generation_progress(session, book, chapters)
                session.commit()
                continue
            if failed:
                book.status = BookStatus.FAILED
                book.failed_stage = "generation"
                book.error_message = failed[0].error_message or f"Chapitre {failed[0].position} en échec."
                book.stage, book.eta_seconds = None, None
                session.add(book)
                session.commit()
                continue
            if any(c.status != ChapterStatus.DONE for c in included):
                book.status = BookStatus.FAILED
                book.failed_stage = "generation"
                book.error_message = "Arrêté par l'utilisateur."
                book.stage, book.eta_seconds = None, None
                session.add(book)
                session.commit()
                continue
            if not included:
                book.status = BookStatus.FAILED
                book.failed_stage = "generation"
                book.error_message = f"Book {book_id} has no chapters — analysis never completed"
                session.add(book)
                session.commit()
                continue
            source_path = book.source_path
            book.stage, book.stage_progress, book.progress = "assembly", 0.0, 90.0
            book.eta_seconds = None
            session.add(book)
            session.commit()

        try:
            audio_path, mp3_path, m4b_path = _assemble_book(engine, book_id, source_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("assemble_book failed for book_id=%d", book_id)
            with Session(engine) as session:
                book = session.get(Book, book_id)
                if book is not None and book.status == BookStatus.GENERATING:
                    book.status = BookStatus.FAILED
                    book.failed_stage = "generation"
                    book.error_message = f"Assemblage : {exc}"
                    book.stage = None
                    session.add(book)
                    session.commit()
            continue
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book is None or book.status != BookStatus.GENERATING:
                continue  # /stop arrivé pendant l'assemblage : on ne l'écrase pas
            book.audio_path, book.mp3_path, book.m4b_path = audio_path, mp3_path, m4b_path
            book.status = BookStatus.DONE
            book.progress, book.stage, book.stage_progress, book.eta_seconds = 100.0, None, 0.0, None
            session.add(book)
            session.commit()


def _enqueue_book_generation(book_id: int, force: bool = False) -> None:
    """Génération d'un livre par la file de chapitres (BE-3) : met en file tous les chapitres
    inclus non terminés puis laisse la pompe les traiter UN PAR TÂCHE Huey — une tâche courte
    (aperçu de voix, régénération d'une réplique) passe donc entre deux chapitres au lieu
    d'attendre la fin du livre entier. Mêmes garde-fous et même reprise que _generate_book_impl.
    """
    from datetime import datetime, timezone

    from app.core.db import get_engine
    from app.core.enums import BookStatus, ChapterStatus
    from app.models import Book, Chapter

    engine = get_engine()
    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None:
            logger.error("generate_book called with unknown book_id=%d", book_id)
            return
        if book.status not in (BookStatus.ANALYZED, BookStatus.DONE, BookStatus.FAILED):
            logger.warning("generate_book skipped: book_id=%d has status=%s", book_id, book.status)
            return
        book.status = BookStatus.GENERATING
        book.progress = 60.0
        book.stage, book.stage_progress, book.eta_seconds = "generation", 0.0, None
        book.error_message = None
        book.failed_stage = None
        session.add(book)
        chapters = session.exec(select(Chapter).where(Chapter.book_id == book_id)).all()
        now = datetime.now(timezone.utc)
        for c in chapters:
            if not c.included or c.status == ChapterStatus.GENERATING:
                continue
            if c.status == ChapterStatus.DONE and not force:
                continue
            c.status = ChapterStatus.PENDING
            c.error_message = None
            c.cancel_requested = False
            c.queued_at = now
            session.add(c)
        session.commit()
    # Rien à générer (tout DONE) ou file à vider : _advance_books conclut, la pompe traite le reste.
    _advance_books(engine)
    _generate_chapter_queue_pump_impl(limit=1)
    _schedule_pump_if_needed(engine)


def _schedule_pump_if_needed(engine) -> None:
    """Ré-enfile la pompe tant qu'il reste des chapitres en file (une tâche Huey par chapitre)."""
    from app.core.enums import ChapterStatus
    from app.models import Chapter

    with Session(engine) as session:
        remaining = session.exec(
            select(Chapter.id).where(
                Chapter.status == ChapterStatus.PENDING, Chapter.queued_at.is_not(None)
            ).limit(1)
        ).first()
    if remaining is not None:
        generate_chapter_queue_pump()


def _generate_book_impl(book_id: int, force: bool = False) -> None:
    from app.core.db import get_engine
    from app.core.enums import BookStatus, ChapterStatus
    from app.models import Book, Chapter

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
        book.status = BookStatus.GENERATING
        book.progress = 0.0
        book.error_message = None
        book.failed_stage = None  # nettoie une valeur périmée d'une tentative précédente
        session.add(book)
        session.commit()

    # Chapters already DONE are reset (and fully resynthesised) ONLY on an
    # explicit force=True — otherwise ALWAYS preserved, whatever the book's
    # previous status, and only whatever is missing gets filled in (audit
    # 2026-07-11: a book left ANALYZED after per-chapter generation — the
    # normal state until "Générer l'audio" is clicked once at the book level
    # — used to have EVERY already-DONE chapter unconditionally reset and
    # resynthesised from scratch, discarding potentially hours of TTS work
    # the moment that button was pressed. Only a resume-after-FAILED used to
    # preserve DONE chapters; that is now the default in every case, and
    # force=True is the explicit separate action for a real full regeneration).
    if force:
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

        # ── Assemble WAV + MP3 + M4B from the per-chapter WAVs already on disk ─────────
        audio_path, mp3_path, m4b_path = _assemble_book(engine, book_id, source_path)

        with Session(engine) as session:
            book = session.get(Book, book_id)
            # Re-check: a /stop could have raced in between the last chapter and
            # here. Never overwrite a FAILED status with DONE.
            if book is None or book.status == BookStatus.FAILED:
                logger.info("generate_book: stop requested just before commit, aborting")
                return
            book.audio_path = audio_path
            book.mp3_path = mp3_path
            book.m4b_path = m4b_path
            book.status = BookStatus.DONE
            book.progress = 100.0
            book.stage = None
            book.stage_progress = 0.0
            book.eta_seconds = None
            session.add(book)
            session.commit()

    except Exception as exc:
        logger.exception("generate_book failed for book_id=%d", book_id)
        with Session(engine) as session:
            book = session.get(Book, book_id)
            if book:
                book.status = BookStatus.FAILED
                book.error_message = str(exc)
                book.failed_stage = "generation"
                session.add(book)
                session.commit()


def _after_tts_use(provider) -> None:
    """Fin d'un usage TTS : un provider qui garde son modèle chargé (cache BE-1) reste en
    mémoire (déchargé à l'inactivité ou sur demande) ; les autres libèrent la VRAM comme avant."""
    if getattr(provider, "keep_loaded", False) is True:
        _touch_tts()
    else:
        _release_qwen_gpu(provider)


async def _synthesise_chapter_worker(
    chapter_id: int, engine, should_abort: Callable[[], bool] | None = None,
) -> tuple[bytes, list[tuple[int, int, int]]] | None:
    """Returns (wav_bytes, [(seg_id, offset_ms, duration_ms)]), or None if
    should_abort() fired before the chapter finished synthesising."""
    from app.models import Book, Chapter
    from app.services.audio.chapter import _synthesise_segments

    settings = get_settings()
    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        book = session.get(Book, chapter.book_id) if chapter else None
        provider = _get_tts_provider(settings, session, book)
        name = _effective_tts_provider(session, book.tts_provider if book else None) \
            or settings.tts_provider
        # Le sel porte aussi l'IDENTITÉ du livre (fichier source, unique par import, et date
        # de création) : SQLite peut réutiliser l'id d'un livre supprimé, et un cache d'un
        # ancien livre ne doit jamais servir au nouveau.
        salt = json.dumps([
            name, _tts_options(session), book.language if book else None,
            book.source_path if book else None, str(book.created_at) if book else None,
        ], sort_keys=True)
        try:
            return await _synthesise_segments(
                chapter_id, session, provider, should_abort=should_abort,
                cache_dir=segment_cache_dir(chapter.book_id, chapter_id), cache_salt=salt,
            )
        finally:
            _after_tts_use(provider)


def segment_cache_dir(book_id: int, chapter_id: int) -> Path:
    """Segments déjà synthétisés d'un chapitre en cours (reprise par segment). Vidé quand le
    chapitre passe DONE."""
    return DATA_DIR / str(book_id) / "segcache" / str(chapter_id)


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


def _generate_chapter_queue_pump_impl(limit: int | None = None) -> None:
    """Pompe la file de génération de chapitres (audit 2026-07-11, Lot 3) : traite
    un chapitre EN FILE (status=PENDING, queued_at renseigné) à la fois, en
    relisant priority DESC puis position ASC à CHAQUE tour de boucle -- pas une
    capture figée au moment de l'enfilage, pour qu'un PATCH .../priority pendant
    l'exécution change réellement le prochain chapitre choisi. S'arrête dès que
    la file est vide, ou après `limit` chapitres (la tâche Huey en traite un seul puis
    se ré-enfile : les tâches courtes passent entre deux). Après chaque chapitre, les
    livres en cours de génération avancent (_advance_books). Suppose un seul worker Huey
    (start.bat -k thread -w 1) -- aucun verrou inter-process n'est nécessaire."""
    from app.core.db import get_engine
    from app.core.enums import ChapterStatus
    from app.models import Chapter

    engine = get_engine()
    processed = 0

    while limit is None or processed < limit:
        with Session(engine) as session:
            next_chapter = session.exec(
                select(Chapter)
                .where(Chapter.status == ChapterStatus.PENDING, Chapter.queued_at.is_not(None))
                .order_by(Chapter.priority.desc(), Chapter.position.asc())
            ).first()
            if next_chapter is None:
                break
            chapter_id = next_chapter.id

        _generate_chapter_impl(chapter_id)
        processed += 1
        _advance_books(engine)

    if processed == 0:
        _advance_books(engine)


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

    from app.core.db import get_engine
    from app.core.enums import VoiceKind
    from app.models.entities import Voice

    settings = get_settings()
    engine = get_engine()
    with Session(engine) as session:
        # Même résolution que la route (_effective_tts_provider) : regarder
        # uniquement settings.tts_provider (.env brut) ignorait la préférence
        # globale AppSetting.preferred_tts_provider, laissant ce no-op se
        # déclencher en silence même quand la route avait accepté la requête
        # sur la base du provider effectif (audit 2026-07-11).
        effective_provider = _effective_tts_provider(session, None) or settings.tts_provider
        if effective_provider != "qwen":
            logger.info(
                "generate_voice_sample: skipped (effective TTS provider=%s)", effective_provider,
            )
            return

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


# ── Aperçu d'une voix sur une réplique du personnage (UX-6) ───────────────────────

_PREVIEW_MAX_CHARS = 220
_PREVIEW_FALLBACK = "Bonjour, ceci est un aperçu de cette voix."


def character_preview_path(session: Session, character, voice_id: str) -> Path:
    """Fichier d'aperçu (personnage, voix). Le nom inclut une empreinte du moteur effectif
    (provider + réglages à chaud + langue du livre) : changer de moteur invalide l'aperçu."""
    import hashlib

    from app.models import Book

    book = session.get(Book, character.book_id)
    provider = _effective_tts_provider(session, book.tts_provider if book else None) \
        or get_settings().tts_provider
    fingerprint = json.dumps([provider, _tts_options(session), book.language if book else None],
                             sort_keys=True)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:8]
    safe_voice = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in voice_id)
    return DATA_DIR / str(character.book_id) / "previews" / f"{character.id}_{safe_voice}_{digest}.wav"


def _preview_text(session: Session, character) -> str:
    """La réplique (dialogue) la plus longue du personnage, tronquée à une fin de phrase :
    c'est sur SON texte qu'on juge si la voix convient."""
    from app.core.enums import SegmentType
    from app.models import Chapter, Segment
    from app.services.audio.format import split_sentences

    chapter_ids = [c for c in session.exec(
        select(Chapter.id).where(Chapter.book_id == character.book_id)
    ).all()]
    best = ""
    if chapter_ids:
        for text in session.exec(
            select(Segment.text).where(
                Segment.character_id == character.id,
                Segment.segment_type == SegmentType.DIALOGUE,
                Segment.chapter_id.in_(chapter_ids),
            ).limit(300)
        ).all():
            if len(text) > len(best):
                best = text
    if not best:
        return _PREVIEW_FALLBACK
    pieces = split_sentences(best, _PREVIEW_MAX_CHARS)
    return pieces[0] if pieces else _PREVIEW_FALLBACK


def _generate_character_preview_impl(character_id: int, voice_id: str) -> None:
    from app.core.db import get_engine
    from app.models import Book, Character
    from app.models.entities import Voice
    from app.services.audio.chapter import _synthesise_with_retry

    engine = get_engine()
    settings = get_settings()
    with Session(engine) as session:
        character = session.get(Character, character_id)
        if character is None:
            logger.error("character preview: unknown character_id=%d", character_id)
            return
        book = session.get(Book, character.book_id)
        from app.services.audio import lexicon as _lexicon
        text = _lexicon.apply(_preview_text(session, character),
                              _lexicon.load_rules(session, character.book_id))
        voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
        ref_path = voice.reference_audio_path if voice else None
        out_path = character_preview_path(session, character, voice_id)
        provider = _get_tts_provider(settings, session, book)
    try:
        wav = asyncio.run(_synthesise_with_retry(
            provider, text, voice_id, emotion=None, reference_audio_path=ref_path,
        ))
    except Exception:  # noqa: BLE001 — l'aperçu ne doit jamais casser le worker
        logger.exception("character preview failed (character=%d voice=%s)", character_id, voice_id)
        return
    finally:
        _after_tts_use(provider)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(wav)


@huey.task(priority=10)
def generate_character_preview(character_id: int, voice_id: str) -> None:
    _generate_character_preview_impl(character_id, voice_id)


# Extrait d'un chapitre avant rendu : ~900 caractères, soit environ une minute d'écoute.
CHAPTER_EXCERPT_MAX_CHARS = 900


def chapter_excerpt_path(session: Session, chapter) -> Path:
    """Fichier de l'extrait d'un chapitre. Le nom inclut une empreinte de tout ce qui change
    le rendu (moteur effectif et ses réglages, langue, voix attribuée à chaque personnage) :
    réattribuer une voix ou changer de moteur invalide l'extrait."""
    import hashlib

    from app.models import Book, Character

    book = session.get(Book, chapter.book_id)
    provider = _effective_tts_provider(session, book.tts_provider if book else None) \
        or get_settings().tts_provider
    voices = sorted(
        (c.id, c.voice_id or "") for c in session.exec(
            select(Character).where(Character.book_id == chapter.book_id)
        ).all()
    )
    fingerprint = json.dumps(
        [provider, _tts_options(session), book.language if book else None, voices,
         CHAPTER_EXCERPT_MAX_CHARS], sort_keys=True,
    )
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:8]
    return DATA_DIR / str(chapter.book_id) / "previews" / f"chapter_{chapter.id}_{digest}.wav"


def designed_voice_id(character) -> str:
    return f"design_b{character.book_id}_c{character.id}"


def _design_character_voice_impl(character_id: int, instruct: str | None = None) -> str | None:
    """Voix CONÇUE d'un personnage (OmniVoice) : une description tirée de sa fiche (ou
    fournie) -> un échantillon de référence -> une voix clonée de la bibliothèque, attribuée
    au personnage. Tout moteur qui clone (OmniVoice, Qwen3-TTS) le fera ensuite parler avec
    CETTE voix d'un bout à l'autre du livre. Retourne le voice_id, ou None en cas d'échec
    (consigné dans les logs : une tâche huey ne doit jamais lever)."""
    from app.core.db import get_engine
    from app.core.enums import VoiceKind
    from app.models import Book, Character
    from app.models.entities import Voice
    from app.services.tts import omnivoice

    engine = get_engine()
    settings = get_settings()
    with Session(engine) as session:
        char = session.get(Character, character_id)
        if char is None:
            logger.error("design voice: unknown character_id=%d", character_id)
            return None
        book = session.get(Book, char.book_id)
        instruct = (instruct or "").strip() or omnivoice.instruct_for_character(
            char.gender, char.age_category, char.voice_quality, char.voice_tone, char.description,
        )
        voice_id = designed_voice_id(char)
        ref = DATA_DIR / "voices" / voice_id / "ref.wav"
        language = book.language if book else None
        options = _tts_options(session) if _effective_tts_provider(
            session, book.tts_provider if book else None) == "omnivoice" else None
        name = f"{char.name} ({book.title if book else 'livre'})"
        gender = char.gender
    try:
        ref_text = asyncio.run(omnivoice.design_voice(settings, instruct, language, ref, options))
    except Exception:  # noqa: BLE001
        logger.exception("design voice failed (character=%d, instruct=%r)", character_id, instruct)
        return None
    (ref.parent / "design.json").write_text(
        json.dumps({"instruct": instruct, "language": language, "engine": "omnivoice"},
                   ensure_ascii=False), encoding="utf-8")
    with Session(engine) as session:
        voice = session.exec(select(Voice).where(Voice.voice_id == voice_id)).first()
        if voice is None:
            voice = Voice(voice_id=voice_id, name=name, kind=VoiceKind.CLONED, gender=gender)
        voice.reference_audio_path = str(ref)
        voice.reference_text = ref_text
        session.add(voice)
        char = session.get(Character, character_id)
        if char is not None:
            char.voice_id = voice_id
            session.add(char)
        session.commit()
    return voice_id


@huey.task(priority=10)  # quelques secondes de GPU : passe avant les chapitres en file
def design_character_voice(character_id: int, instruct: str | None = None) -> None:
    _design_character_voice_impl(character_id, instruct)


def _generate_chapter_excerpt_impl(chapter_id: int) -> None:
    from app.core.db import get_engine
    from app.models import Book, Chapter
    from app.services.audio.chapter import synthesise_chapter_excerpt

    engine = get_engine()
    settings = get_settings()
    with Session(engine) as session:
        chapter = session.get(Chapter, chapter_id)
        if chapter is None:
            logger.error("chapter excerpt: unknown chapter_id=%d", chapter_id)
            return
        book = session.get(Book, chapter.book_id)
        out_path = chapter_excerpt_path(session, chapter)
        provider = _get_tts_provider(settings, session, book)
        try:
            wav = asyncio.run(synthesise_chapter_excerpt(
                chapter_id, session, provider, CHAPTER_EXCERPT_MAX_CHARS,
            ))
        except Exception:  # noqa: BLE001 — l'extrait ne doit jamais casser le worker
            logger.exception("chapter excerpt failed (chapter=%d)", chapter_id)
            return
        finally:
            _after_tts_use(provider)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(wav)


@huey.task(priority=10)  # tâche courte : passe avant les chapitres en file
def generate_chapter_excerpt(chapter_id: int) -> None:
    _generate_chapter_excerpt_impl(chapter_id)


@huey.on_startup()
def _reconcile_zombie_state() -> None:
    """Runs once when the Huey consumer (re)starts. A Book left PROCESSING or
    GENERATING, or a Chapter left GENERATING, can only mean the PREVIOUS
    worker process died mid-task (SqliteHuey never replays a task it already
    picked up, and this app runs exactly one worker) — nothing can
    legitimately still be "in flight" the instant this process starts. Left
    alone, a zombie Book is only reachable through an undocumented detour
    (/stop happens to accept PROCESSING/GENERATING even with no worker alive
    to see it), and a zombie standalone Chapter has NO way out at all:
    regenerating it 409s ("already generating"), and its own /stop just sets
    a flag nothing will ever poll again. Sweeping both here on startup turns
    that dead end into the normal FAILED/PENDING state the existing
    resume/retry UI already knows how to handle (audit 2026-07-11)."""
    from app.core.db import get_engine
    from app.core.enums import BookStatus, ChapterStatus
    from app.models import Book, Chapter

    engine = get_engine()
    with Session(engine) as session:
        zombie_books = session.exec(
            select(Book).where(Book.status.in_((BookStatus.PROCESSING, BookStatus.GENERATING)))
        ).all()
        for book in zombie_books:
            # Lire le statut D'ORIGINE avant de l'écraser -- c'est lui qui dit
            # quelle étape était en cours (audit 2026-07-11, T2.3).
            book.failed_stage = "analysis" if book.status == BookStatus.PROCESSING else "generation"
            book.status = BookStatus.FAILED
            book.error_message = "Worker interrompu (redémarrage) — reprendre l'analyse/génération."
            session.add(book)

        zombie_chapters = session.exec(
            select(Chapter).where(Chapter.status == ChapterStatus.GENERATING)
        ).all()
        for chapter in zombie_chapters:
            chapter.status = ChapterStatus.PENDING
            chapter.cancel_requested = False
            chapter.error_message = None
            session.add(chapter)

        session.commit()

    if zombie_books or zombie_chapters:
        logger.warning(
            "worker startup: reconciled %d zombie book(s), %d zombie chapter(s)",
            len(zombie_books), len(zombie_chapters),
        )


@huey.task(priority=10)  # tâche courte : passe avant les chapitres en file
def generate_voice_sample(voice_id: str) -> None:
    _generate_voice_sample_impl(voice_id)


@huey.task()
def analyze_book(book_id: int, force: bool = False) -> None:
    _analyze_book_impl(book_id, force)


@huey.task()
def generate_book(book_id: int, force: bool = False) -> None:
    _enqueue_book_generation(book_id, force)


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
        from app.services.audio import lexicon as _lexicon
        seg_text = _lexicon.apply(segment.text, _lexicon.load_rules(session, chapter.book_id))
        book_id = chapter.book_id

        v = session.exec(_select(Voice).where(Voice.voice_id == voice_id)).first()
        ref_path = v.reference_audio_path if v else None

        provider = _get_tts_provider(settings, session, book)

    try:
        wav_bytes = await _synthesise_with_retry(
            provider, seg_text, voice_id,
            emotion=emotion, reference_audio_path=ref_path,
        )
    finally:
        _after_tts_use(provider)

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


@huey.task(priority=10)
def generate_segment(take_id: int) -> None:
    _generate_segment_impl(take_id)


@huey.task()
def generate_chapter_queue_pump() -> None:
    """Un chapitre par tâche, puis ré-enfilage tant que la file n'est pas vide."""
    from app.core.db import get_engine

    _generate_chapter_queue_pump_impl(limit=1)
    _schedule_pump_if_needed(get_engine())


@huey.task(priority=10)
def release_qwen_vram() -> None:
    """Décharge les modèles TTS gardés en mémoire (POST /models/qwen/unload)."""
    n = _release_all_tts()
    logger.info("release_qwen_vram: %d provider(s) déchargé(s)", n)


@huey.periodic_task(crontab(minute="*"))
def _unload_idle_tts() -> None:
    """Libère la VRAM d'un modèle TTS inutilisé depuis TTS_IDLE_UNLOAD_SECONDS (BE-1)."""
    idle = get_settings().tts_idle_unload_seconds
    if idle > 0 and _TTS_CACHE and time.monotonic() - _TTS_LAST_USED > idle:
        n = _release_all_tts()
        logger.info("modèle TTS inactif depuis > %ds : %d provider(s) déchargé(s)", idle, n)


@huey.task()
def process_book(book_id: int) -> None:
    _process_book_impl(book_id)
