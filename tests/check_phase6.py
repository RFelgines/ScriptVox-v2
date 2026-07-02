"""Phase 6 verification — per-chapter audio endpoint.
Run: .venv/Scripts/python tests/check_phase6.py
"""
import asyncio
import io
import os
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p6.db",
    "HUEY_DB_PATH": "./huey_test_p6.db",
    "DATA_DIR": "./data_test",
    "PIPER_VOICES_DIR": "./voices",
    "PIPER_BINARY_PATH": sys.executable,
})

_n = 0


def section(title: str) -> None:
    global _n
    _n += 1
    print(f"\n[{_n}] {title}")


def ok(msg: str) -> None:
    print(f"    ok  {msg}")


def die(msg: str) -> None:
    print(f"  FAIL  {msg}")
    sys.exit(1)


def _make_wav_bytes(n_frames: int, framerate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ── 1. Imports ────────────────────────────────────────────────────────────────
section("Phase 6 modules import cleanly")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.services.audio.assembler import assemble_wav, assemble_wav_bytes  # noqa: E402
from app.services.audio.chapter import synthesise_chapter  # noqa: E402
from app.models.entities import Book, Chapter, Character, Segment  # noqa: E402
from app.core.enums import BookStatus, ChapterStatus, Gender, SegmentType  # noqa: E402
ok("assemble_wav_bytes, synthesise_chapter, models, enums")


# ── Shared builders ───────────────────────────────────────────────────────────

def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_mock_tts() -> MagicMock:
    m = MagicMock()
    m.synthesise = AsyncMock(return_value=_make_wav_bytes(50))
    return m


def _seed_done_book(engine) -> tuple[int, int]:
    """Insert a DONE book with one chapter (position 1) holding a NARRATION
    segment and a DIALOGUE segment voiced by a character. Returns (book_id, chapter_id)."""
    with Session(engine) as s:
        book = Book(title="Seeded", source_path="/tmp/seed.epub", status=BookStatus.DONE)
        s.add(book)
        s.commit()
        s.refresh(book)
        book_id = book.id

        ch = Chapter(book_id=book_id, position=1, title="Ch1", raw_text="x")
        s.add(ch)
        s.commit()
        s.refresh(ch)
        chapter_id = ch.id

        char = Character(book_id=book_id, name="Alice", gender=Gender.FEMALE, voice_id="female_0")
        s.add(char)
        s.commit()
        s.refresh(char)

        s.add(Segment(chapter_id=chapter_id, position=1, text="Once.",
                      segment_type=SegmentType.NARRATION))
        s.add(Segment(chapter_id=chapter_id, position=2, text="Hello!",
                      segment_type=SegmentType.DIALOGUE, character_id=char.id,
                      emotion="furious"))
        s.commit()
    return book_id, chapter_id


# ── 2. assemble_wav_bytes happy path + empty guard ───────────────────────────
section("assemble_wav_bytes() returns valid WAV bytes; raises on empty input")
_seg1, _seg2, _seg3 = _make_wav_bytes(100), _make_wav_bytes(200), _make_wav_bytes(50)
_wav_bytes = assemble_wav_bytes([_seg1, _seg2, _seg3])
assert _wav_bytes[:4] == b"RIFF", f"Expected RIFF header, got {_wav_bytes[:4]!r}"
with wave.open(io.BytesIO(_wav_bytes), "rb") as _wf:
    assert _wf.getnframes() == 350, f"Expected 350 frames, got {_wf.getnframes()}"
    assert _wf.getnchannels() == 1
    assert _wf.getframerate() == 22050
ok("3 segments -> 350-frame WAV bytes, 1ch / 22050 Hz")

try:
    assemble_wav_bytes([])
    die("Expected ValueError on empty segment list")
except ValueError as exc:
    ok(f"ValueError on empty input: {exc}")

# assemble_wav (path-based) still works — no regression from the refactor
with tempfile.TemporaryDirectory() as _td:
    _out = assemble_wav([_seg1, _seg2], Path(_td) / "out.wav")
    with wave.open(str(_out), "rb") as _wf:
        assert _wf.getnframes() == 300, f"Expected 300 frames, got {_wf.getnframes()}"
    ok("assemble_wav (path) unchanged: 2 segments -> 300 frames")


# ── 3. synthesise_chapter happy path ─────────────────────────────────────────
section("synthesise_chapter() synthesises a chapter's segments into WAV bytes")
_engine = _make_test_engine()
_book_id, _chapter_id = _seed_done_book(_engine)
_mock_tts = _make_mock_tts()

with Session(_engine) as _s:
    _wav = asyncio.run(synthesise_chapter(_chapter_id, _s, _mock_tts))

assert _wav[:4] == b"RIFF", f"Expected RIFF header, got {_wav[:4]!r}"
with wave.open(io.BytesIO(_wav), "rb") as _wf:
    assert _wf.getnframes() == 100, f"Expected 100 frames (2x50), got {_wf.getnframes()}"
ok(f"2 segments -> 100-frame WAV bytes ({len(_wav)} bytes)")

# Narrator vs character voice routing: NARRATION -> 'narrator', DIALOGUE -> 'female_0'
_called_voices = {call.args[1] for call in _mock_tts.synthesise.call_args_list}
assert _called_voices == {"narrator", "female_0"}, f"Unexpected voices: {_called_voices}"
ok(f"Voice routing correct: {_called_voices}")

# B2 : l'émotion du segment est transmise à synthesise (kwarg 'emotion')
# NARRATION -> emotion=None ; DIALOGUE (seed) -> emotion="furious"
_emotions = {call.kwargs.get("emotion") for call in _mock_tts.synthesise.call_args_list}
assert _emotions == {None, "furious"}, f"émotion non transmise: {_emotions}"
ok(f"emotion forwarded to synthesise: {_emotions}")


# ── 4. synthesise_chapter on empty chapter raises ValueError ─────────────────
section("synthesise_chapter() raises ValueError when chapter has no segments")
with Session(_engine) as _s:
    _empty_ch = Chapter(book_id=_book_id, position=2, title="Empty", raw_text="")
    _s.add(_empty_ch)
    _s.commit()
    _s.refresh(_empty_ch)
    _empty_ch_id = _empty_ch.id

with Session(_engine) as _s:
    try:
        asyncio.run(synthesise_chapter(_empty_ch_id, _s, _make_mock_tts()))
        die("Expected ValueError on chapter with no segments")
    except ValueError as exc:
        ok(f"ValueError raised: {exc}")


# ── 5-8. Endpoint behaviour via TestClient ───────────────────────────────────
section("GET /books/{id}/chapters/{n}/audio — 200 / 404 / 409 paths")
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import get_session  # noqa: E402

_api_engine = _make_test_engine()


def _override_session():
    with Session(_api_engine) as s:
        yield s


app.dependency_overrides[get_session] = _override_session

with tempfile.TemporaryDirectory() as _api_tmp:
    # Write a real WAV to disk for the happy-path test
    _api_wav = Path(_api_tmp) / "ch1.wav"
    _api_wav.write_bytes(_make_wav_bytes(100))

    # Book with a DONE chapter pointing to the real WAV file
    with Session(_api_engine) as _s:
        _api_book = Book(title="DoneChBook", source_path="/tmp/x.epub", status=BookStatus.DONE)
        _s.add(_api_book)
        _s.commit()
        _s.refresh(_api_book)
        _api_book_id = _api_book.id

        _api_ch = Chapter(
            book_id=_api_book_id, position=1, title="Ch1", raw_text="x",
            status=ChapterStatus.DONE, audio_path=str(_api_wav),
        )
        _s.add(_api_ch)
        _s.commit()

    # Book with a PENDING chapter (for the 409 path)
    with Session(_api_engine) as _s:
        _pending_book = Book(title="PendingCh", source_path="/tmp/y.epub",
                             status=BookStatus.ANALYZED)
        _s.add(_pending_book)
        _s.commit()
        _s.refresh(_pending_book)
        _pending_book_id = _pending_book.id

        _s.add(Chapter(book_id=_pending_book_id, position=1, raw_text="x"))
        _s.commit()

    with TestClient(app, raise_server_exceptions=False) as _tc:
        # 200 — happy path: serves persisted WAV file
        _r = _tc.get(f"/books/{_api_book_id}/chapters/1/audio")
        assert _r.status_code == 200, f"Expected 200, got {_r.status_code} ({_r.text})"
        assert "audio" in _r.headers.get("content-type", ""), \
            f"Expected audio content-type, got {_r.headers.get('content-type')}"
        assert _r.content[:4] == b"RIFF", f"Expected WAV body, got {_r.content[:4]!r}"
        ok("200 with valid WAV from persisted file")

        # 404 — book inexistant
        _r = _tc.get("/books/9999/chapters/1/audio")
        assert _r.status_code == 404, f"Expected 404, got {_r.status_code}"
        ok("404 when book_id not found")

        # 409 — chapter status=PENDING (not yet generated)
        _r = _tc.get(f"/books/{_pending_book_id}/chapters/1/audio")
        assert _r.status_code == 409, f"Expected 409, got {_r.status_code}"
        ok("409 when chapter status != DONE")

        # 404 — position de chapitre inexistante
        _r = _tc.get(f"/books/{_api_book_id}/chapters/99/audio")
        assert _r.status_code == 404, f"Expected 404, got {_r.status_code}"
        ok("404 when chapter position does not exist")

app.dependency_overrides.clear()


print("\nPHASE 6 (per-chapter audio) OK\n")
