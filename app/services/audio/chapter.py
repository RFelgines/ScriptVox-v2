import asyncio
import logging
import re
from typing import Callable

from sqlmodel import Session, select

from app.core.enums import SegmentType
from app.models.entities import Character, Segment, Voice
from app.services.audio.assembler import assemble_wav_bytes
from app.services.audio.format import (
    adjust_level,
    normalize_audio,
    silence_wav,
    split_sentences,
    wav_duration_ms,
)
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

# Silence entre deux morceaux d'une même réplique découpée (TTS-5).
_SPLIT_PAUSE_MS = 150

# Au moins une lettre ou un chiffre (toutes écritures) : sinon rien à prononcer.
_SPEAKABLE = re.compile(r"[^\W_]")

# Ré-export (rétrocompatibilité des tests / imports existants).
_wav_duration_ms = wav_duration_ms


class _AudioSettings:
    """Réglages d'assemblage, valeurs nettoyées (int/bool). Robuste à un `get_settings`
    remplacé par un mock dans les tests : toute valeur du mauvais type retombe sur le défaut."""

    def __init__(self, raw) -> None:
        def _int(name: str, default: int) -> int:
            v = getattr(raw, name, default)
            return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else default

        def _bool(name: str, default: bool) -> bool:
            v = getattr(raw, name, default)
            return v if isinstance(v, bool) else default

        self.pause_same_voice_ms = _int("pause_same_voice_ms", 250)
        self.pause_voice_change_ms = _int("pause_voice_change_ms", 450)
        self.audio_normalize = _bool("audio_normalize", True)
        self.tts_max_chars = _int("tts_max_chars", 0)
        self.tts_concurrency = _int("tts_concurrency", 0)


def _audio_settings() -> _AudioSettings:
    """Import paresseux : ce module est importé par des tests qui posent leur environnement
    après coup."""
    from app.config import get_settings
    return _AudioSettings(get_settings())


def pause_after_ms(voice_id: str, next_voice_id: str | None, settings=None) -> int:
    """Silence inséré après une réplique : plus court si la même voix enchaîne, plus long
    quand la voix change (AUD-1, audit 2026-09-25). 0 après la dernière réplique."""
    if next_voice_id is None:
        return 0
    s = settings or _audio_settings()
    return s.pause_same_voice_ms if voice_id == next_voice_id else s.pause_voice_change_ms


async def _synthesise_with_retry(
    tts: BaseTTSProvider, text: str, voice_id: str,
    emotion: str | None, reference_audio_path: str | None,
) -> bytes:
    """Up to _TTS_MAX_RETRIES attempts, spaced by _TTS_RETRY_DELAY seconds — no
    delay after the last attempt, whether it succeeds or the exception is finally
    re-raised. La sortie est normalisée (WAV mono 16 bits 24 kHz) : un provider peut donc
    renvoyer n'importe quel format audio décodable.

    Un texte sans aucune lettre ni chiffre (« ) », « * * * », « … ») n'est pas envoyé au
    moteur : il n'y a rien à prononcer, et EdgeTTS répond alors « No audio was received »,
    ce qui faisait échouer le chapitre entier après trois essais (rapport de nuit
    2026-09-27 : segment « ) » d'Alice, chapitre IV). Il devient un silence nul."""
    if not _SPEAKABLE.search(text):
        return silence_wav(0)
    last_exc: Exception | None = None
    for attempt in range(_TTS_MAX_RETRIES):
        try:
            chunk = await tts.synthesise(
                text, voice_id, emotion=emotion, reference_audio_path=reference_audio_path,
            )
            chunk = normalize_audio(chunk)
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


async def _synthesise_text(
    tts: BaseTTSProvider, text: str, voice_id: str,
    emotion: str | None, reference_audio_path: str | None, settings,
) -> bytes:
    """Synthétise le texte d'un segment. Un texte plus long que la limite du provider est
    découpé aux fins de phrase puis recollé (TTS-5) : une narration d'une page envoyée d'un
    bloc fait dériver ou tronquer la plupart des TTS neuronaux. Le niveau sonore du segment
    est homogénéisé (AUD-4) si AUDIO_NORMALIZE est actif."""
    tts_limit = getattr(tts, "max_chars", 0)
    limit = settings.tts_max_chars or (tts_limit if isinstance(tts_limit, int) else 0)
    pieces = split_sentences(text, limit) if limit else [text]
    if not pieces:
        pieces = [text]
    parts: list[bytes] = []
    for i, piece in enumerate(pieces):
        if i > 0:
            parts.append(silence_wav(_SPLIT_PAUSE_MS))
        parts.append(await _synthesise_with_retry(
            tts, piece, voice_id, emotion=emotion, reference_audio_path=reference_audio_path,
        ))
    audio = parts[0] if len(parts) == 1 else assemble_wav_bytes(parts)
    if settings.audio_normalize:
        audio = adjust_level(audio)
    return audio


def _prefix_within(segments: list, max_chars: int) -> list:
    """Premiers segments dont le texte cumulé tient dans `max_chars` (toujours au moins un)."""
    out, total = [], 0
    for seg in segments:
        total += len(seg.text or "")
        if out and total > max_chars:
            break
        out.append(seg)
    return out


async def _synthesise_segments(
    chapter_id: int,
    session: Session,
    tts: BaseTTSProvider,
    should_abort: Callable[[], bool] | None = None,
    max_chars: int | None = None,
) -> tuple[bytes, list[tuple[int, int, int]]] | None:
    """Synthesise all segments and compute per-segment timing.

    `max_chars` limite la synthèse aux premiers segments (au moins un) dont le texte cumulé
    tient dans cette taille : c'est l'extrait écouté avant de lancer le rendu complet, avec
    exactement les mêmes voix, émotions, pauses et niveaux que le chapitre final.

    Returns (assembled_wav_bytes, [(seg_id, offset_ms, duration_ms), ...]), or None
    if should_abort() returned True before the last segment was synthesised —
    callers must discard everything computed so far for this chapter (nothing here
    is persisted; the whole chapter is meant to be redone from scratch on the next
    attempt, see _generate_chapter_async). Passed by book-driven generation
    (Lot C, audit 2026-07-02, polling Book.status) and by standalone chapter
    generation (polling Chapter.cancel_requested, see _make_chapter_stop_checker).

    Les offsets incluent les silences insérés entre répliques (la surbrillance de la
    transcription en dépend) ; `duration_ms` est la durée parlée seule.
    """
    settings = _audio_settings()
    segments = session.exec(
        select(Segment).where(Segment.chapter_id == chapter_id).order_by(Segment.position)
    ).all()

    if not segments:
        raise ValueError(f"Chapter {chapter_id} has no segments to synthesise")
    if max_chars is not None:
        segments = _prefix_within(segments, max_chars)

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

    voice_ids: list[str] = [
        NARRATOR_VOICE_ID
        if seg.segment_type == SegmentType.NARRATION or seg.character_id is None
        else char_voice.get(seg.character_id, NARRATOR_VOICE_ID)
        for seg in segments
    ]

    # Synthesise grouped by checkpoint (non-cloned first, then cloned) instead of
    # narrative order. Qwen3-TTS can't keep both checkpoints loaded on a 10 Go GPU
    # (qwen.py _ensure_model/_ensure_base_model unload one before loading the
    # other); a chapter where cloned and preset voices alternate in narrative
    # order was measured reloading a ~3-4 Go checkpoint 10-12 times (real HP
    # book), fragmenting the CUDA allocator until VRAM saturated and spilled into
    # system RAM. Grouping caps that at 1 swap per chapter regardless of playback
    # order (2026-07-02, RAM/VRAM investigation). The final WAV/timing are
    # reassembled in narrative order below, independent of synthesis order.
    non_cloned = [i for i, vid in enumerate(voice_ids) if ref_path.get(vid) is None]
    cloned = [i for i, vid in enumerate(voice_ids) if ref_path.get(vid) is not None]

    # Concurrence (BE-2) : un moteur cloud (EdgeTTS…) est borné par la latence réseau, pas par
    # la machine ; plusieurs requêtes en vol divisent la durée d'autant. 1 = séquentiel (GPU
    # local). Les tâches sont créées dans l'ordre : avec un sémaphore de 1, l'ordre
    # « non clonées puis clonées » est conservé exactement.
    tts_conc = getattr(tts, "supports_concurrency", 1)
    concurrency = max(1, settings.tts_concurrency or (tts_conc if isinstance(tts_conc, int) else 1))
    semaphore = asyncio.Semaphore(concurrency)
    chunks: dict[int, bytes] = {}
    aborted = False

    async def _run(i: int) -> None:
        nonlocal aborted
        async with semaphore:
            if aborted or (should_abort is not None and should_abort()):
                aborted = True
                return
            chunks[i] = await _synthesise_text(
                tts, segments[i].text, voice_ids[i],
                emotion=segments[i].emotion,
                reference_audio_path=ref_path.get(voice_ids[i]),
                settings=settings,
            )

    jobs = [asyncio.ensure_future(_run(i)) for i in non_cloned + cloned]
    try:
        await asyncio.gather(*jobs)
    except BaseException:
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        raise
    if aborted:
        return None

    wav_chunks: list[bytes] = []
    timing: list[tuple[int, int, int]] = []  # (seg_id, offset_ms, duration_ms)
    offset = 0
    for i, seg in enumerate(segments):
        chunk = chunks[i]
        dur = wav_duration_ms(chunk)
        timing.append((seg.id, offset, dur))
        wav_chunks.append(chunk)
        offset += dur
        gap = pause_after_ms(
            voice_ids[i], voice_ids[i + 1] if i + 1 < len(segments) else None, settings,
        )
        if gap:
            wav_chunks.append(silence_wav(gap))
            offset += gap

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


async def synthesise_chapter_excerpt(
    chapter_id: int, session: Session, tts: BaseTTSProvider, max_chars: int,
) -> bytes:
    """Extrait du début du chapitre, rendu comme le chapitre final (voir max_chars)."""
    wav, _ = await _synthesise_segments(chapter_id, session, tts, max_chars=max_chars)
    return wav
