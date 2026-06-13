"""Phase 5 verification — end-to-end integration test of _process_book_impl.
Run: .venv/Scripts/python tests/check_phase5.py
"""
import io
import os
import shutil
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE_EPUB = ROOT / "tests" / "fixtures" / "test.epub"

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p5.db",
    "HUEY_DB_PATH": "./huey_test_p5.db",
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
section("All integration modules import cleanly")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.workers.tasks import _process_book_impl  # noqa: E402
from app.models.entities import Book, Character  # noqa: E402
from app.core.enums import BookStatus, Gender, SegmentType  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402
from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData  # noqa: E402
ok("_process_book_impl, models, enums, LLMChapterResult, TTSError")


# ── 2. Test fixture exists ────────────────────────────────────────────────────
section("Test EPUB fixture exists")
if not FIXTURE_EPUB.exists():
    die(f"Missing test fixture: {FIXTURE_EPUB}")
ok(f"Found: {FIXTURE_EPUB.name} ({FIXTURE_EPUB.stat().st_size} bytes)")


# ── Shared builders ───────────────────────────────────────────────────────────

def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_mock_llm() -> MagicMock:
    result = LLMChapterResult(
        characters=[
            CharacterData(
                name="Alice",
                description="Protagonist",
                gender=Gender.FEMALE,
                voice_tone="soft",
            ),
        ],
        segments=[
            SegmentData(
                position=1,
                text="Once upon a time.",
                segment_type=SegmentType.NARRATION,
                character_name=None,
            ),
            SegmentData(
                position=2,
                text="Hello!",
                segment_type=SegmentType.DIALOGUE,
                character_name="Alice",
            ),
        ],
    )
    m = MagicMock()
    m.analyze = AsyncMock(return_value=result)
    return m


def _make_mock_tts() -> MagicMock:
    m = MagicMock()
    m.synthesise = AsyncMock(return_value=_make_wav_bytes(50))
    return m


# ── 3. Happy path: Book.status == DONE ────────────────────────────────────────
section("Happy path: _process_book_impl completes — Book.status == DONE")

_hp_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _hp_tmp:
    _hp_epub = Path(_hp_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _hp_epub)

    with Session(_hp_engine) as _s:
        _hp_book = Book(title="Pending", source_path=str(_hp_epub))
        _s.add(_hp_book)
        _s.commit()
        _s.refresh(_hp_book)
        _hp_book_id = _hp_book.id

    with (
        patch("app.core.db.get_engine", return_value=_hp_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_make_mock_llm()),
        patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()),
    ):
        _process_book_impl(_hp_book_id)

    with Session(_hp_engine) as _s:
        _hp_b = _s.get(Book, _hp_book_id)
        if _hp_b.status == BookStatus.FAILED:
            die(f"Book FAILED unexpectedly — error_message={_hp_b.error_message!r}")
        assert _hp_b.status == BookStatus.DONE, f"Expected DONE, got {_hp_b.status}"
        assert _hp_b.progress == 100.0, f"Expected progress=100.0, got {_hp_b.progress}"
        assert _hp_b.audio_path is not None, "audio_path must not be None"
        _hp_audio_path = _hp_b.audio_path
    ok(f"status=DONE, progress=100.0, audio_path={Path(_hp_audio_path).name!r}")

    _hp_audio = Path(_hp_audio_path)
    assert _hp_audio.exists(), f"Audio file not on disk: {_hp_audio}"
    with wave.open(str(_hp_audio), "rb") as _wf:
        _hp_nframes = _wf.getnframes()
        _hp_nchannels = _wf.getnchannels()
        _hp_framerate = _wf.getframerate()
    assert _hp_nframes > 0, "WAV file is empty"
    assert _hp_nchannels == 1, f"Expected 1 channel, got {_hp_nchannels}"
    assert _hp_framerate == 22050, f"Expected 22050 Hz, got {_hp_framerate}"
    ok(f"WAV valid on disk: {_hp_nframes} frames, {_hp_nchannels}ch, {_hp_framerate}Hz")

    # ── 4. All Characters have voice_id ───────────────────────────────────────
    section("Happy path: all Character.voice_id populated after pipeline")
    with Session(_hp_engine) as _s:
        _hp_chars = _s.exec(
            select(Character).where(Character.book_id == _hp_book_id)
        ).all()
        if not _hp_chars:
            die("No characters in DB — LLM mock was not called correctly")
        for _c in _hp_chars:
            assert _c.voice_id is not None, f"Character {_c.name!r} has no voice_id"
            ok(f"  {_c.name!r} ({_c.gender.value}) => voice_id={_c.voice_id!r}")


# ── 5. Failure path: TTSError → Book.status == FAILED ────────────────────────
section("Failure path: TTSError in synthesise -> Book.status == FAILED")

_fail_engine = _make_test_engine()
_fail_tts = MagicMock()
_fail_tts.synthesise = AsyncMock(
    side_effect=TTSError("piper:narrator", RuntimeError("synthesis failed"))
)

with tempfile.TemporaryDirectory() as _fail_tmp:
    _fail_epub = Path(_fail_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _fail_epub)

    with Session(_fail_engine) as _s:
        _fail_book = Book(title="WillFail", source_path=str(_fail_epub))
        _s.add(_fail_book)
        _s.commit()
        _s.refresh(_fail_book)
        _fail_book_id = _fail_book.id

    with (
        patch("app.core.db.get_engine", return_value=_fail_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_make_mock_llm()),
        patch("app.services.tts.factory.get_tts_provider", return_value=_fail_tts),
    ):
        _process_book_impl(_fail_book_id)

    with Session(_fail_engine) as _s:
        _fail_b = _s.get(Book, _fail_book_id)
        assert _fail_b.status == BookStatus.FAILED, (
            f"Expected FAILED, got {_fail_b.status}"
        )
        assert _fail_b.error_message, "error_message must not be empty on failure"
        ok(f"status=FAILED, error_message={_fail_b.error_message!r}")


print("\nPHASE 5 (integration) OK\n")
