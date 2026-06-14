"""Phase 7 Étape 1a — split worker: _analyze_book_impl / _generate_book_impl.
Run: .venv/Scripts/python tests/check_phase7.py
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p7.db",
    "HUEY_DB_PATH": "./huey_test_p7.db",
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
section("Phase 7 modules import cleanly")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.workers.tasks import _analyze_book_impl, _generate_book_impl  # noqa: E402
from app.models.entities import Book, Chapter, Character, Segment  # noqa: E402
from app.core.enums import BookStatus, Gender, SegmentType  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402
from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData  # noqa: E402
ok("_analyze_book_impl, _generate_book_impl, BookStatus.ANALYZED/GENERATING")


# ── 2. Enum sanity ────────────────────────────────────────────────────────────
section("BookStatus exposes ANALYZED and GENERATING values")
assert BookStatus.ANALYZED.value == "ANALYZED", f"Got {BookStatus.ANALYZED.value!r}"
assert BookStatus.GENERATING.value == "GENERATING", f"Got {BookStatus.GENERATING.value!r}"
ok("ANALYZED='ANALYZED', GENERATING='GENERATING'")


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


def _seed_analyzed_book(engine, epub_path: str) -> int:
    """Seed an ANALYZED book with one chapter and one NARRATION segment."""
    with Session(engine) as s:
        book = Book(
            title="Analyzed", source_path=epub_path, status=BookStatus.ANALYZED
        )
        s.add(book)
        s.commit()
        s.refresh(book)
        book_id = book.id

        ch = Chapter(book_id=book_id, position=1, title="Ch1", raw_text="x")
        s.add(ch)
        s.commit()
        s.refresh(ch)

        s.add(Segment(
            chapter_id=ch.id, position=1, text="Once.",
            segment_type=SegmentType.NARRATION,
        ))
        s.commit()
    return book_id


# ── 3. _analyze_book_impl happy path ─────────────────────────────────────────
section("_analyze_book_impl: parse+LLM+voices -> ANALYZED, audio_path=None")

if not FIXTURE_EPUB.exists():
    die(f"Missing test fixture: {FIXTURE_EPUB}")

_ha_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _ha_tmp:
    _ha_epub = Path(_ha_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _ha_epub)

    with Session(_ha_engine) as _s:
        _ha_book = Book(title="Pending", source_path=str(_ha_epub))
        _s.add(_ha_book)
        _s.commit()
        _s.refresh(_ha_book)
        _ha_book_id = _ha_book.id

    with (
        patch("app.core.db.get_engine", return_value=_ha_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_make_mock_llm()),
    ):
        _analyze_book_impl(_ha_book_id)

    with Session(_ha_engine) as _s:
        _ha_b = _s.get(Book, _ha_book_id)
        if _ha_b.status == BookStatus.FAILED:
            die(f"_analyze_book_impl FAILED unexpectedly: {_ha_b.error_message!r}")
        assert _ha_b.status == BookStatus.ANALYZED, (
            f"Expected ANALYZED, got {_ha_b.status}"
        )
        assert _ha_b.progress == 100.0, f"Expected 100.0, got {_ha_b.progress}"
        assert _ha_b.audio_path is None, (
            f"audio_path must be None after analysis, got {_ha_b.audio_path!r}"
        )
    ok("status=ANALYZED, progress=100.0, audio_path=None")

    with Session(_ha_engine) as _s:
        _ha_chars = _s.exec(select(Character).where(Character.book_id == _ha_book_id)).all()
        assert _ha_chars, "No characters in DB — LLM mock was not called"
        for _c in _ha_chars:
            assert _c.voice_id is not None, f"Character {_c.name!r} has no voice_id"
        ok(f"voice_id populated: {[(c.name, c.voice_id) for c in _ha_chars]}")


# ── 4. _analyze_book_impl failure (LLM exception) → FAILED ──────────────────
section("_analyze_book_impl: LLM exception -> FAILED, error_message set")

_af_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _af_tmp:
    _af_epub = Path(_af_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _af_epub)

    with Session(_af_engine) as _s:
        _af_book = Book(title="WillFail", source_path=str(_af_epub))
        _s.add(_af_book)
        _s.commit()
        _s.refresh(_af_book)
        _af_book_id = _af_book.id

    _fail_llm = MagicMock()
    _fail_llm.analyze = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with (
        patch("app.core.db.get_engine", return_value=_af_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_fail_llm),
    ):
        _analyze_book_impl(_af_book_id)

    with Session(_af_engine) as _s:
        _af_b = _s.get(Book, _af_book_id)
        assert _af_b.status == BookStatus.FAILED, f"Expected FAILED, got {_af_b.status}"
        assert _af_b.error_message, "error_message must be set on failure"
        ok(f"status=FAILED, error_message={_af_b.error_message!r}")


# ── 5. _generate_book_impl on ANALYZED book → DONE ───────────────────────────
section("_generate_book_impl: ANALYZED+segment+TTS mock -> DONE, WAV on disk")

_hg_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _hg_tmp:
    _hg_epub = Path(_hg_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _hg_epub)
    _hg_book_id = _seed_analyzed_book(_hg_engine, str(_hg_epub))

    with (
        patch("app.core.db.get_engine", return_value=_hg_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()),
    ):
        _generate_book_impl(_hg_book_id)

    with Session(_hg_engine) as _s:
        _hg_b = _s.get(Book, _hg_book_id)
        if _hg_b.status == BookStatus.FAILED:
            die(f"_generate_book_impl FAILED unexpectedly: {_hg_b.error_message!r}")
        assert _hg_b.status == BookStatus.DONE, f"Expected DONE, got {_hg_b.status}"
        assert _hg_b.progress == 100.0, f"Expected 100.0, got {_hg_b.progress}"
        assert _hg_b.audio_path, "audio_path must be set after generation"
        _hg_audio_path = _hg_b.audio_path
    ok(f"status=DONE, progress=100.0, audio_path={Path(_hg_audio_path).name!r}")

    _hg_audio = Path(_hg_audio_path)
    assert _hg_audio.exists(), f"WAV not on disk: {_hg_audio}"
    with wave.open(str(_hg_audio), "rb") as _wf:
        assert _wf.getnframes() > 0, "WAV file is empty"
    ok(f"WAV valid on disk: {_hg_audio.stat().st_size} bytes")


# ── 6. _generate_book_impl guard: PENDING → no-op ────────────────────────────
section("_generate_book_impl guard: PENDING book -> status unchanged, no audio")

_gg_engine = _make_test_engine()

with Session(_gg_engine) as _s:
    _gg_book = Book(title="StillPending", source_path="/tmp/nofile.epub")
    _s.add(_gg_book)
    _s.commit()
    _s.refresh(_gg_book)
    _gg_book_id = _gg_book.id

with patch("app.core.db.get_engine", return_value=_gg_engine):
    _generate_book_impl(_gg_book_id)

with Session(_gg_engine) as _s:
    _gg_b = _s.get(Book, _gg_book_id)
    assert _gg_b.status == BookStatus.PENDING, f"Expected PENDING, got {_gg_b.status}"
    assert _gg_b.audio_path is None, "audio_path must remain None"
ok("PENDING book skipped: status=PENDING, audio_path=None unchanged")


# ── 7. _generate_book_impl failure (TTSError) → FAILED ───────────────────────
section("_generate_book_impl: TTSError -> FAILED, error_message set")

_gf_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _gf_tmp:
    _gf_epub = Path(_gf_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _gf_epub)
    _gf_book_id = _seed_analyzed_book(_gf_engine, str(_gf_epub))

    _fail_tts = MagicMock()
    _fail_tts.synthesise = AsyncMock(
        side_effect=TTSError("piper:narrator", RuntimeError("synthesis failed"))
    )

    with (
        patch("app.core.db.get_engine", return_value=_gf_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_fail_tts),
    ):
        _generate_book_impl(_gf_book_id)

    with Session(_gf_engine) as _s:
        _gf_b = _s.get(Book, _gf_book_id)
        assert _gf_b.status == BookStatus.FAILED, f"Expected FAILED, got {_gf_b.status}"
        assert _gf_b.error_message, "error_message must be set on failure"
        ok(f"status=FAILED, error_message={_gf_b.error_message!r}")


# ── 8-10. HTTP route changes ──────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
import app.api.routes.books as books_module  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.workers.tasks import analyze_book as _analyze_book_task  # noqa: E402

_rb_engine = _make_test_engine()


def _rb_session():
    with Session(_rb_engine) as s:
        yield s


app.dependency_overrides[get_session] = _rb_session

# Section 8: POST /books triggers analyze_book, not process_book
section("POST /books triggers analyze_book (not process_book)")
_analyze_calls: list = []
books_module.analyze_book = lambda book_id: _analyze_calls.append(book_id)

with TestClient(app) as _tc:
    with open(str(FIXTURE_EPUB), "rb") as _fh:
        _r8 = _tc.post("/books", files={"file": ("test.epub", _fh, "application/epub+zip")})
    assert _r8.status_code == 202, f"Expected 202, got {_r8.status_code} ({_r8.text})"
    _r8_book_id = _r8.json()["id"]

books_module.analyze_book = _analyze_book_task  # restore

assert _analyze_calls == [_r8_book_id], (
    f"Expected analyze_book([{_r8_book_id}]), got {_analyze_calls}"
)
ok(f"POST /books -> 202, analyze_book called with book_id={_r8_book_id}")

# Section 9: chapter audio returns 200 for ANALYZED book
section("GET /books/{id}/chapters/1/audio — 200 when status=ANALYZED")

with tempfile.TemporaryDirectory() as _r9_tmp:
    _r9_epub = Path(_r9_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _r9_epub)
    _r9_book_id = _seed_analyzed_book(_rb_engine, str(_r9_epub))

    with patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()):
        with TestClient(app, raise_server_exceptions=False) as _tc:
            _r9 = _tc.get(f"/books/{_r9_book_id}/chapters/1/audio")

    assert _r9.status_code == 200, f"Expected 200, got {_r9.status_code} ({_r9.text})"
    assert _r9.content[:4] == b"RIFF", f"Expected WAV body, got {_r9.content[:4]!r}"
    ok("200 with valid WAV for ANALYZED book")

# Section 10: chapter audio still 409 for PROCESSING book
section("GET /books/{id}/chapters/1/audio — 409 when status=PROCESSING")

with Session(_rb_engine) as _s:
    _r10_book = Book(
        title="InProgress", source_path="/tmp/x.epub", status=BookStatus.PROCESSING
    )
    _s.add(_r10_book)
    _s.commit()
    _s.refresh(_r10_book)
    _r10_book_id = _r10_book.id

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r10 = _tc.get(f"/books/{_r10_book_id}/chapters/1/audio")

assert _r10.status_code == 409, f"Expected 409, got {_r10.status_code}"
ok("409 for PROCESSING book (guard still applies)")

app.dependency_overrides.clear()


# ── 11-13. POST /books/{id}/generate ─────────────────────────────────────────
from app.workers.tasks import generate_book as _generate_book_task  # noqa: E402

_gen_engine = _make_test_engine()


def _gen_session():
    with Session(_gen_engine) as s:
        yield s


app.dependency_overrides[get_session] = _gen_session

# Section 11: 202 + generate_book dispatched for ANALYZED book
section("POST /books/{id}/generate — 202, generate_book dispatched for ANALYZED book")

with Session(_gen_engine) as _s:
    _g11_book = Book(
        title="ReadyToGenerate", source_path="/tmp/r.epub", status=BookStatus.ANALYZED
    )
    _s.add(_g11_book)
    _s.commit()
    _s.refresh(_g11_book)
    _g11_book_id = _g11_book.id

_generate_calls: list = []
books_module.generate_book = lambda book_id: _generate_calls.append(book_id)

with TestClient(app) as _tc:
    _r11 = _tc.post(f"/books/{_g11_book_id}/generate")
    assert _r11.status_code == 202, f"Expected 202, got {_r11.status_code} ({_r11.text})"
    assert _r11.json()["status"] == "ANALYZED", (
        f"Expected ANALYZED in response, got {_r11.json()['status']}"
    )

books_module.generate_book = _generate_book_task  # restore

assert _generate_calls == [_g11_book_id], (
    f"Expected generate_book([{_g11_book_id}]), got {_generate_calls}"
)
ok(f"202, generate_book called with book_id={_g11_book_id}")

# Section 12: 404 if book not found
section("POST /books/{id}/generate — 404 if book not found")

books_module.generate_book = lambda book_id: None

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r12 = _tc.post("/books/9999/generate")
    assert _r12.status_code == 404, f"Expected 404, got {_r12.status_code}"

books_module.generate_book = _generate_book_task  # restore
ok("404 for non-existent book")

# Section 13: 409 for status != ANALYZED
section("POST /books/{id}/generate — 409 for PENDING, DONE, PROCESSING")

_g13_status_cases = [BookStatus.PENDING, BookStatus.DONE, BookStatus.PROCESSING]
_g13_ids: dict = {}

with Session(_gen_engine) as _s:
    for _st in _g13_status_cases:
        _b = Book(title=f"Bad_{_st.value}", source_path="/tmp/x.epub", status=_st)
        _s.add(_b)
        _s.commit()
        _s.refresh(_b)
        _g13_ids[_st] = _b.id

books_module.generate_book = lambda book_id: None

with TestClient(app, raise_server_exceptions=False) as _tc:
    for _st in _g13_status_cases:
        _r13 = _tc.post(f"/books/{_g13_ids[_st]}/generate")
        assert _r13.status_code == 409, (
            f"Expected 409 for status={_st.value}, got {_r13.status_code}"
        )
        ok(f"409 for status={_st.value}")

books_module.generate_book = _generate_book_task  # restore

app.dependency_overrides.clear()


print("\nPHASE 7 (split worker + route + generate trigger) OK\n")
