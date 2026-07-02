import asyncio
import io
import logging
import wave
from typing import Callable

from sqlmodel import Session, select

from app.core.enums import SegmentType
from app.models.entities import Character, Segment, Voice
from app.services.audio.assembler import assemble_wav_bytes
from app.services.tts.base import BaseTTSProvider
from app.services.voice_assignment import NARRATOR_VOICE_ID

logger = logging.getLogger(__name__)

# Calqué sur le retry LLM (tasks.py _analyze_book, ARCHITECTURE.md §2.5) : la
# synthèse TTS n'avait NI retry NI persistance partielle avant ce lot (audit
# 2026-07-02, finding M6 résiduel) -- un flake réseau unique sur un segment
# faisait échouer tout le chapitre. Délai plus court que le retry LLM (30s) : un
# flake TTS est typiquement un blip réseau transitoire, pas une saturation VRAM
# nécessitant un temps de récupération long.
_TTS_MAX_RETRIES = 3
_TTS_RETRY_DELAY = 3  # secondes


def _wav_duration_ms(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return int(w.getnframes() / w.getframerate() * 1000)


async def _synthesise_with_retry(
    tts: BaseTTSProvider, text: str, voice_id: str,
    emotion: str | None, reference_audio_path: str | None,
) -> bytes:
    """Up to _TTS_MAX_RETRIES attempts, spaced by _TTS_RETRY_DELAY seconds — no
    delay after the last attempt, whether it succeeds or the exception is finally
    re-raised."""
    last_exc: Exception | None = None
    for attempt in range(_TTS_MAX_RETRIES):
        try:
            chunk = await tts.synthesise(
                text, voice_id, emotion=emotion, reference_audio_path=reference_audio_path,
            )
            if attempt > 0:
                logger.info(
                    "synthesise_with_retry: succeeded on attempt %d/%d",
                    attempt + 1, _TTS_MAX_RETRIES,
                )
            return chunk
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "synthesise_with_retry: attempt %d/%d failed: %s",
                attempt + 1, _TTS_MAX_RETRIES, exc,
            )
            if attempt < _TTS_MAX_RETRIES - 1:
                await asyncio.sleep(_TTS_RETRY_DELAY)
    raise last_exc


async def _synthesise_segments(
    chapter_id: int,
    session: Session,
    tts: BaseTTSProvider,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[bytes, list[tuple[int, int, int]]] | None:
    """Synthesise all segments and compute per-segment timing.

    Returns (assembled_wav_bytes, [(seg_id, offset_ms, duration_ms), ...]), or None
    if should_abort() returned True before the last segment was synthesised —
    callers must discard everything computed so far for this chapter (nothing here
    is persisted; the whole chapter is meant to be redone from scratch on the next
    attempt, see _generate_chapter_async). should_abort is only ever passed by
    book-driven generation (Lot C, audit 2026-07-02); a standalone chapter
    generation has no such concept since it never tracks Book.status.
    """
    segments = session.exec(
        select(Segment).where(Segment.chapter_id == chapter_id).order_by(Segment.position)
    ).all()

    if not segments:
        raise ValueError(f"Chapter {chapter_id} has no segments to synthesise")

    char_voice: dict[int, str] = {}
    for seg in segments:
        if seg.character_id and seg.character_id not in char_voice:
            char = session.get(Character, seg.character_id)
            if char and char.voice_id:
                char_voice[seg.character_id] = char.voice_id

    all_voice_ids: set[str] = set(char_voice.values()) | {NARRATOR_VOICE_ID}
    ref_path: dict[str, str | None] = {}
    for vid in all_voice_ids:
        v = session.exec(select(Voice).where(Voice.voice_id == vid)).first()
        ref_path[vid] = v.reference_audio_path if v else None

    wav_chunks: list[bytes] = []
    timing: list[tuple[int, int, int]] = []  # (seg_id, offset_ms, duration_ms)
    offset = 0

    for seg in segments:
        if should_abort is not None and should_abort():
            return None

        voice_id = (
            NARRATOR_VOICE_ID
            if seg.segment_type == SegmentType.NARRATION or seg.character_id is None
            else char_voice.get(seg.character_id, NARRATOR_VOICE_ID)
        )
        chunk = await _synthesise_with_retry(
            tts, seg.text, voice_id,
            emotion=seg.emotion,
            reference_audio_path=ref_path.get(voice_id),
        )
        dur = _wav_duration_ms(chunk)
        timing.append((seg.id, offset, dur))
        offset += dur
        wav_chunks.append(chunk)

    return assemble_wav_bytes(wav_chunks), timing


async def synthesise_chapter(
    chapter_id: int,
    session: Session,
    tts: BaseTTSProvider,
) -> bytes:
    """Synthesise every segment of a single chapter and return assembled WAV bytes.

    Raises ValueError if the chapter has no segments.
    """
    wav, _ = await _synthesise_segments(chapter_id, session, tts)
    return wav
