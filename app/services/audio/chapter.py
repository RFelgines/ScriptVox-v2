from sqlmodel import Session, select

from app.core.enums import SegmentType
from app.models.entities import Character, Segment, Voice
from app.services.audio.assembler import assemble_wav_bytes
from app.services.tts.base import BaseTTSProvider
from app.services.voice_assignment import NARRATOR_VOICE_ID


async def synthesise_chapter(
    chapter_id: int,
    session: Session,
    tts: BaseTTSProvider,
) -> bytes:
    """Synthesise every segment of a single chapter and assemble them into WAV bytes.

    Voice routing mirrors the book-level worker: NARRATION (or any segment without
    a character) uses the narrator voice; dialogue uses the speaking character's
    assigned voice, falling back to the narrator if none is set.

    Raises ValueError if the chapter has no segments.
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

    # Look up reference_audio_path once per unique voice_id (one query per voice, not per segment)
    all_voice_ids: set[str] = set(char_voice.values()) | {NARRATOR_VOICE_ID}
    ref_path: dict[str, str | None] = {}
    for vid in all_voice_ids:
        v = session.exec(select(Voice).where(Voice.voice_id == vid)).first()
        ref_path[vid] = v.reference_audio_path if v else None

    wav_chunks: list[bytes] = []
    for seg in segments:
        voice_id = (
            NARRATOR_VOICE_ID
            if seg.segment_type == SegmentType.NARRATION or seg.character_id is None
            else char_voice.get(seg.character_id, NARRATOR_VOICE_ID)
        )
        wav_chunks.append(await tts.synthesise(
            seg.text, voice_id,
            emotion=seg.emotion,
            reference_audio_path=ref_path.get(voice_id),
        ))

    return assemble_wav_bytes(wav_chunks)
