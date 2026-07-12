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
        assert _ha_b.language == "en", (
            f"language must be auto-extracted from dc:language, got {_ha_b.language!r}"
        )
    ok("status=ANALYZED, progress=100.0, audio_path=None, language='en' (auto-extrait)")

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

# Section 8b: DATA_DIR.mkdir(parents=True) — fonctionne même si le PARENT
# de DATA_DIR n'existe pas encore (audit 2026-07-11). Avant fix,
# DATA_DIR.mkdir(exist_ok=True) seul levait FileNotFoundError -> 500 dès le
# premier upload sur une config DATA_DIR="storage/data" avec "storage/" absent
# (voices.py/le worker créent déjà leurs sous-dossiers avec parents=True).
section("POST /books — DATA_DIR.mkdir(parents=True) même si son parent n'existe pas encore")
books_module.analyze_book = lambda book_id: _analyze_calls.append(book_id)
with tempfile.TemporaryDirectory() as _r8b_tmp:
    _orig_data_dir = books_module.DATA_DIR
    books_module.DATA_DIR = Path(_r8b_tmp) / "storage" / "data"  # "storage/" absent
    try:
        with TestClient(app, raise_server_exceptions=False) as _tc:
            with open(str(FIXTURE_EPUB), "rb") as _fh:
                _r8b = _tc.post("/books", files={"file": ("test.epub", _fh, "application/epub+zip")})
        assert _r8b.status_code == 202, f"Expected 202, got {_r8b.status_code} ({_r8b.text})"
    finally:
        books_module.DATA_DIR = _orig_data_dir
books_module.analyze_book = _analyze_book_task  # restore
ok("upload réussit même si DATA_DIR a un parent inexistant (storage/ créé récursivement)")

# Section 8c: DELETE /books/{id} — os.remove best-effort (audit 2026-07-11).
# Un fichier verrouillé par le lecteur audio (Windows, plateforme cible) ne
# doit pas faire échouer la suppression avec un 500 après que la ligne DB a
# déjà été effacée -- même logique que rmtree(ignore_errors=True) juste après.
section("DELETE /books/{id} — os.remove best-effort, pas de 500 si un fichier est verrouillé")
with tempfile.TemporaryDirectory() as _rdel_tmp:
    _del_epub = Path(_rdel_tmp) / "locked.epub"
    _del_epub.write_bytes(b"fake epub content")
    with Session(_rb_engine) as _s:
        _del_book = Book(title="Locked", source_path=str(_del_epub), status=BookStatus.DONE)
        _s.add(_del_book)
        _s.commit()
        _s.refresh(_del_book)
        _del_book_id = _del_book.id

    with patch("app.api.routes.books.os.remove", side_effect=PermissionError("simulated lock")):
        with TestClient(app, raise_server_exceptions=False) as _tc:
            _rdel = _tc.delete(f"/books/{_del_book_id}")
    assert _rdel.status_code == 204, f"Expected 204, got {_rdel.status_code} ({_rdel.text})"

    with Session(_rb_engine) as _s:
        assert _s.get(Book, _del_book_id) is None, "Book row devrait être supprimée malgré l'échec du fichier"
ok("204 malgré un fichier verrouillé (PermissionError avalée), ligne DB supprimée quand même")

# Section 9: chapter audio -> 409 when chapter is PENDING (not yet generated)
section("GET /books/{id}/chapters/1/audio — 409 when chapter is PENDING (not yet generated)")

with tempfile.TemporaryDirectory() as _r9_tmp:
    _r9_epub = Path(_r9_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _r9_epub)
    _r9_book_id = _seed_analyzed_book(_rb_engine, str(_r9_epub))

    with TestClient(app, raise_server_exceptions=False) as _tc:
        _r9 = _tc.get(f"/books/{_r9_book_id}/chapters/1/audio")

    assert _r9.status_code == 409, f"Expected 409 (chapter PENDING), got {_r9.status_code} ({_r9.text})"
    ok("409 when chapter.status=PENDING (must call POST /generate first)")

# Section 10: chapter audio -> 404 when chapter not found
section("GET /books/{id}/chapters/1/audio — 404 when chapter not found")

with Session(_rb_engine) as _s:
    _r10_book = Book(title="NoChapters", source_path="/tmp/x.epub", status=BookStatus.ANALYZED)
    _s.add(_r10_book)
    _s.commit()
    _s.refresh(_r10_book)
    _r10_book_id = _r10_book.id

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r10 = _tc.get(f"/books/{_r10_book_id}/chapters/1/audio")

assert _r10.status_code == 404, f"Expected 404, got {_r10.status_code}"
ok("404 when chapter position does not exist")

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
    # Analyse complète (audit 2026-07-11) : un chapitre avec segment, sinon la
    # route rejette désormais en 409 ("analyse incomplète") avant dispatch.
    _g11_ch = Chapter(book_id=_g11_book_id, position=1, title="Ch1", raw_text="x")
    _s.add(_g11_ch)
    _s.commit()
    _s.refresh(_g11_ch)
    _s.add(Segment(chapter_id=_g11_ch.id, position=1, text="x", segment_type=SegmentType.NARRATION))
    _s.commit()

_generate_calls: list = []
books_module.generate_book = lambda book_id, force=False: _generate_calls.append((book_id, force))

with TestClient(app) as _tc:
    _r11 = _tc.post(f"/books/{_g11_book_id}/generate")
    assert _r11.status_code == 202, f"Expected 202, got {_r11.status_code} ({_r11.text})"
    assert _r11.json()["status"] == "ANALYZED", (
        f"Expected ANALYZED in response, got {_r11.json()['status']}"
    )

books_module.generate_book = _generate_book_task  # restore

assert _generate_calls == [(_g11_book_id, False)], (
    f"Expected generate_book(({_g11_book_id}, False)), got {_generate_calls}"
)
ok(f"202, generate_book(book_id={_g11_book_id}, force=False) — défaut sans query param")

# Section 11b: ?force=true transmis à generate_book (audit 2026-07-11, T2.1)
section("POST /books/{id}/generate?force=true — force=True transmis à generate_book")
_generate_calls_force: list = []
books_module.generate_book = lambda book_id, force=False: _generate_calls_force.append((book_id, force))

with TestClient(app) as _tc:
    _r11b = _tc.post(f"/books/{_g11_book_id}/generate?force=true")
    assert _r11b.status_code == 202, f"Expected 202, got {_r11b.status_code} ({_r11b.text})"

books_module.generate_book = _generate_book_task  # restore

assert _generate_calls_force == [(_g11_book_id, True)], (
    f"Expected generate_book(({_g11_book_id}, True)), got {_generate_calls_force}"
)
ok(f"202, generate_book(book_id={_g11_book_id}, force=True) — query param transmis")

# Section 12: 404 if book not found
section("POST /books/{id}/generate — 404 if book not found")

books_module.generate_book = lambda book_id, force=False: None

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r12 = _tc.post("/books/9999/generate")
    assert _r12.status_code == 404, f"Expected 404, got {_r12.status_code}"

books_module.generate_book = _generate_book_task  # restore
ok("404 for non-existent book")

# Section 13: 409 for status != ANALYZED/DONE (DONE autorisé depuis la régénération)
section("POST /books/{id}/generate — 409 for PENDING, PROCESSING")

_g13_status_cases = [BookStatus.PENDING, BookStatus.PROCESSING]
_g13_ids: dict = {}

with Session(_gen_engine) as _s:
    for _st in _g13_status_cases:
        _b = Book(title=f"Bad_{_st.value}", source_path="/tmp/x.epub", status=_st)
        _s.add(_b)
        _s.commit()
        _s.refresh(_b)
        _g13_ids[_st] = _b.id

books_module.generate_book = lambda book_id, force=False: None

with TestClient(app, raise_server_exceptions=False) as _tc:
    for _st in _g13_status_cases:
        _r13 = _tc.post(f"/books/{_g13_ids[_st]}/generate")
        assert _r13.status_code == 409, (
            f"Expected 409 for status={_st.value}, got {_r13.status_code}"
        )
        ok(f"409 for status={_st.value}")

books_module.generate_book = _generate_book_task  # restore

app.dependency_overrides.clear()


# ── 14-16. Étape 3a — ChapterStatus enum + Chapter fields + ChapterResponse ───
from app.core.enums import ChapterStatus  # noqa: E402
from app.schemas.book import ChapterResponse  # noqa: E402

_3a_engine = _make_test_engine()

# Section 14: ChapterStatus has exactly 4 expected values
section("ChapterStatus enum — PENDING/GENERATING/DONE/FAILED")
assert ChapterStatus.PENDING.value    == "PENDING"
assert ChapterStatus.GENERATING.value == "GENERATING"
assert ChapterStatus.DONE.value       == "DONE"
assert ChapterStatus.FAILED.value     == "FAILED"
assert len(ChapterStatus) == 4, f"Expected 4 values, got {len(ChapterStatus)}"
ok("ChapterStatus: 4 values OK")

# Section 15: Chapter model round-trip with new fields
section("Chapter model — audio_path / status / error_message round-trip")

with Session(_3a_engine) as _s:
    _3a_book = Book(title="Sch3a", source_path="/tmp/x.epub")
    _s.add(_3a_book)
    _s.commit()
    _s.refresh(_3a_book)
    _3a_book_id = _3a_book.id

    _3a_ch = Chapter(
        book_id=_3a_book_id,
        position=1,
        title="Ch1",
        raw_text="text",
        status=ChapterStatus.DONE,
        audio_path="/data/1/ch1.wav",
        error_message=None,
    )
    _s.add(_3a_ch)
    _s.commit()
    _s.refresh(_3a_ch)
    _3a_ch_id = _3a_ch.id

with Session(_3a_engine) as _s:
    _3a_loaded = _s.get(Chapter, _3a_ch_id)
    assert _3a_loaded.status      == ChapterStatus.DONE,       f"status={_3a_loaded.status!r}"
    assert _3a_loaded.audio_path  == "/data/1/ch1.wav",        f"audio_path={_3a_loaded.audio_path!r}"
    assert _3a_loaded.error_message is None,                   f"error_message={_3a_loaded.error_message!r}"
    ok(f"status=DONE, audio_path='/data/1/ch1.wav', error_message=None")

# Check default (PENDING)
with Session(_3a_engine) as _s:
    _3a_ch2 = Chapter(book_id=_3a_book_id, position=2, raw_text="y")
    _s.add(_3a_ch2)
    _s.commit()
    _s.refresh(_3a_ch2)
    assert _3a_ch2.status     == ChapterStatus.PENDING, f"default status={_3a_ch2.status!r}"
    assert _3a_ch2.audio_path is None,                  f"default audio_path={_3a_ch2.audio_path!r}"
    ok("default status=PENDING, audio_path=None")

# Section 16: ChapterResponse round-trip from ORM Chapter
section("ChapterResponse — from_attributes round-trip from Chapter ORM")

with Session(_3a_engine) as _s:
    _3a_src = _s.get(Chapter, _3a_ch_id)
    _3a_resp = ChapterResponse.model_validate(_3a_src)
    assert _3a_resp.id            == _3a_ch_id
    assert _3a_resp.position      == 1
    assert _3a_resp.title         == "Ch1"
    assert _3a_resp.status        == ChapterStatus.DONE
    assert _3a_resp.error_message is None
    ok(f"ChapterResponse: id={_3a_resp.id}, position=1, title='Ch1', status=DONE")

# Failure state
with Session(_3a_engine) as _s:
    _3a_failed_ch = Chapter(
        book_id=_3a_book_id, position=3, raw_text="z",
        status=ChapterStatus.FAILED,
        error_message="TTS exploded",
    )
    _s.add(_3a_failed_ch)
    _s.commit()
    _s.refresh(_3a_failed_ch)
    _3a_resp_f = ChapterResponse.model_validate(_3a_failed_ch)
    assert _3a_resp_f.status        == ChapterStatus.FAILED
    assert _3a_resp_f.error_message == "TTS exploded"
    ok("FAILED chapter: status=FAILED, error_message='TTS exploded'")


# ── 17-20. Étape 3b — _generate_chapter_impl + POST /chapters/{n}/generate ───
from app.workers.tasks import _generate_chapter_impl, generate_chapter_queue_pump as _generate_chapter_queue_pump_task  # noqa: E402


def _get_chapter_id(engine, book_id: int) -> int:
    with Session(engine) as _s:
        _ch = _s.exec(select(Chapter).where(Chapter.book_id == book_id)).first()
        return _ch.id


# Section 17: _generate_chapter_impl happy path -> DONE + WAV on disk
section("_generate_chapter_impl: happy path -> chapter DONE, WAV on disk")

_c17_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _c17_tmp:
    _c17_epub = Path(_c17_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _c17_epub)
    _c17_book_id = _seed_analyzed_book(_c17_engine, str(_c17_epub))
    _c17_ch_id = _get_chapter_id(_c17_engine, _c17_book_id)

    with (
        patch("app.core.db.get_engine", return_value=_c17_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()),
    ):
        _generate_chapter_impl(_c17_ch_id)

    with Session(_c17_engine) as _s:
        _c17_ch = _s.get(Chapter, _c17_ch_id)
        if _c17_ch.status == ChapterStatus.FAILED:
            die(f"_generate_chapter_impl FAILED: {_c17_ch.error_message!r}")
        assert _c17_ch.status == ChapterStatus.DONE, f"Expected DONE, got {_c17_ch.status}"
        assert _c17_ch.audio_path, "audio_path must be set"
        _c17_audio = Path(_c17_ch.audio_path)
    ok(f"status=DONE, audio_path={_c17_audio.name!r}")

    assert _c17_audio.exists(), f"WAV not on disk: {_c17_audio}"
    with wave.open(str(_c17_audio), "rb") as _wf:
        assert _wf.getnframes() > 0, "WAV file is empty"
    ok(f"WAV valid on disk: {_c17_audio.stat().st_size} bytes")


# Section 18: _generate_chapter_impl failure -> FAILED + error_message
section("_generate_chapter_impl: TTSError -> chapter FAILED, error_message set")

_c18_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _c18_tmp:
    _c18_epub = Path(_c18_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _c18_epub)
    _c18_book_id = _seed_analyzed_book(_c18_engine, str(_c18_epub))
    _c18_ch_id = _get_chapter_id(_c18_engine, _c18_book_id)

    _c18_fail_tts = MagicMock()
    _c18_fail_tts.synthesise = AsyncMock(
        side_effect=TTSError("piper:narrator", RuntimeError("chapter tts failed"))
    )

    with (
        patch("app.core.db.get_engine", return_value=_c18_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_c18_fail_tts),
    ):
        _generate_chapter_impl(_c18_ch_id)

    with Session(_c18_engine) as _s:
        _c18_ch = _s.get(Chapter, _c18_ch_id)
        assert _c18_ch.status == ChapterStatus.FAILED, f"Expected FAILED, got {_c18_ch.status}"
        assert _c18_ch.error_message, "error_message must be set"
        ok(f"status=FAILED, error_message={_c18_ch.error_message!r}")


# Section 19: POST /books/{id}/chapters/{n}/generate -> 202 + dispatch
section("POST /books/{id}/chapters/{n}/generate — 202, queued_at posé + pompe dispatchée")

_c19_engine = _make_test_engine()


def _c19_session():
    with Session(_c19_engine) as _s:
        yield _s


app.dependency_overrides[get_session] = _c19_session

with tempfile.TemporaryDirectory() as _c19_tmp:
    _c19_epub = Path(_c19_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _c19_epub)
    _c19_book_id = _seed_analyzed_book(_c19_engine, str(_c19_epub))
    _c19_ch_id = _get_chapter_id(_c19_engine, _c19_book_id)

    _pump_calls19: list = []
    books_module.generate_chapter_queue_pump = lambda: _pump_calls19.append(1)

    with TestClient(app) as _tc:
        _r19 = _tc.post(f"/books/{_c19_book_id}/chapters/1/generate")
        assert _r19.status_code == 202, f"Expected 202, got {_r19.status_code} ({_r19.text})"
        _r19_data = _r19.json()
        assert _r19_data["position"] == 1, f"Expected position=1, got {_r19_data['position']}"
        assert _r19_data["status"] == "PENDING", f"Expected PENDING, got {_r19_data['status']}"

    books_module.generate_chapter_queue_pump = _generate_chapter_queue_pump_task  # restore

    assert len(_pump_calls19) == 1, f"Expected pump dispatched once, got {len(_pump_calls19)}"
    with Session(_c19_engine) as _s:
        _c19_ch_after = _s.get(Chapter, _c19_ch_id)
        assert _c19_ch_after.queued_at is not None, "Expected queued_at to be set"
    ok(f"202, queued_at posé + pompe dispatchée (chapter_id={_c19_ch_id})")

# Section 20: route guards (404 book, 404 chapter, 409 non-ANALYZED)
section("POST /books/{id}/chapters/{n}/generate — 404/409 guards")

with Session(_c19_engine) as _s:
    _c20_done_book = Book(
        title="DoneBook", source_path="/tmp/d.epub", status=BookStatus.DONE
    )
    _s.add(_c20_done_book)
    _s.commit()
    _s.refresh(_c20_done_book)
    _c20_done_id = _c20_done_book.id

books_module.generate_chapter_queue_pump = lambda: None

with TestClient(app, raise_server_exceptions=False) as _tc:
    # 404 book not found
    _r20a = _tc.post("/books/9999/chapters/1/generate")
    assert _r20a.status_code == 404, f"Expected 404, got {_r20a.status_code}"
    ok("404 for non-existent book")

    # 409 book status != ANALYZED
    _r20b = _tc.post(f"/books/{_c20_done_id}/chapters/1/generate")
    assert _r20b.status_code == 409, f"Expected 409 for DONE book, got {_r20b.status_code}"
    ok("409 for DONE book")

    # 404 chapter not found
    _r20c = _tc.post(f"/books/{_c19_book_id}/chapters/999/generate")
    assert _r20c.status_code == 404, f"Expected 404 for missing chapter, got {_r20c.status_code}"
    ok("404 for non-existent chapter position")

books_module.generate_chapter_queue_pump = _generate_chapter_queue_pump_task  # restore
app.dependency_overrides.clear()


# ── 21-23. Étape 3c — serve persisted + listing + re-dispatch ────────────────

_c3c_engine = _make_test_engine()


def _c3c_session():
    with Session(_c3c_engine) as _s:
        yield _s


app.dependency_overrides[get_session] = _c3c_session

# Section 21: GET /chapters/{n}/audio — 200, serves persisted WAV when DONE
section("GET /books/{id}/chapters/{n}/audio — 200 serves persisted WAV when chapter DONE")

with tempfile.TemporaryDirectory() as _c21_tmp:
    # Write a real WAV to disk that the endpoint will serve
    _c21_wav_path = Path(_c21_tmp) / "ch1.wav"
    _c21_wav_path.write_bytes(_make_wav_bytes(100))

    with Session(_c3c_engine) as _s:
        _c21_book = Book(title="DoneChapters", source_path="/tmp/x.epub", status=BookStatus.ANALYZED)
        _s.add(_c21_book)
        _s.commit()
        _s.refresh(_c21_book)
        _c21_book_id = _c21_book.id

        _c21_ch = Chapter(
            book_id=_c21_book_id, position=1, title="Ch1", raw_text="x",
            status=ChapterStatus.DONE, audio_path=str(_c21_wav_path),
        )
        _s.add(_c21_ch)
        _s.commit()

    with TestClient(app, raise_server_exceptions=False) as _tc:
        _r21 = _tc.get(f"/books/{_c21_book_id}/chapters/1/audio")

    assert _r21.status_code == 200, f"Expected 200, got {_r21.status_code} ({_r21.text})"
    assert _r21.content[:4] == b"RIFF", f"Expected WAV body, got {_r21.content[:4]!r}"
    ok(f"200 with valid WAV ({len(_r21.content)} bytes) from persisted file")

section("GET /books/{id}/chapters/{n}/audio — 404 (pas 500) si DONE avec audio_path=None (audit 2026-07-11)")
# Incohérence défensive (base ancienne, édition manuelle) : un chapitre DONE
# sans audio_path faisait planter Path(None) en TypeError -> 500, alors que
# l'assembleur livre (tasks.py) filtre déjà ce cas avec `if c.audio_path`.
with Session(_c3c_engine) as _s:
    _c21b_book = Book(title="DoneNoPath", source_path="/tmp/y.epub", status=BookStatus.ANALYZED)
    _s.add(_c21b_book)
    _s.commit()
    _s.refresh(_c21b_book)
    _c21b_book_id = _c21b_book.id
    _c21b_ch = Chapter(
        book_id=_c21b_book_id, position=1, title="Ch1", raw_text="x",
        status=ChapterStatus.DONE, audio_path=None,
    )
    _s.add(_c21b_ch)
    _s.commit()

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r21b = _tc.get(f"/books/{_c21b_book_id}/chapters/1/audio")
assert _r21b.status_code == 404, f"Expected 404, got {_r21b.status_code} ({_r21b.text})"
ok("404 propre (pas 500/TypeError) sur DONE + audio_path=None")

# Section 22: GET /books/{id}/chapters — list[ChapterResponse]
section("GET /books/{id}/chapters — list[ChapterResponse] ordered by position")

with Session(_c3c_engine) as _s:
    _c22_book = Book(title="MultiChapter", source_path="/tmp/y.epub", status=BookStatus.ANALYZED)
    _s.add(_c22_book)
    _s.commit()
    _s.refresh(_c22_book)
    _c22_book_id = _c22_book.id

    for _pos in (1, 2, 3):
        _s.add(Chapter(book_id=_c22_book_id, position=_pos, raw_text=f"text{_pos}"))
    _s.commit()

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r22 = _tc.get(f"/books/{_c22_book_id}/chapters")

assert _r22.status_code == 200, f"Expected 200, got {_r22.status_code} ({_r22.text})"
_r22_data = _r22.json()
assert len(_r22_data) == 3, f"Expected 3 chapters, got {len(_r22_data)}"
assert [c["position"] for c in _r22_data] == [1, 2, 3], "Chapters not ordered by position"
assert all(c["status"] == "PENDING" for c in _r22_data), "Default status should be PENDING"
ok(f"GET /chapters: 3 chapters, positions {[c['position'] for c in _r22_data]}, all PENDING")

# 404 for unknown book
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r22b = _tc.get("/books/9999/chapters")
assert _r22b.status_code == 404, f"Expected 404, got {_r22b.status_code}"
ok("404 for non-existent book")

# Section 23: POST /chapters/{n}/generate re-dispatch when chapter already DONE
section("POST /books/{id}/chapters/{n}/generate — 202 re-dispatch when chapter already DONE")

with Session(_c3c_engine) as _s:
    _c23_book = Book(title="RegenBook", source_path="/tmp/z.epub", status=BookStatus.ANALYZED)
    _s.add(_c23_book)
    _s.commit()
    _s.refresh(_c23_book)
    _c23_book_id = _c23_book.id

    _c23_ch = Chapter(
        book_id=_c23_book_id, position=1, raw_text="x",
        status=ChapterStatus.DONE, audio_path="/data/1/ch1.wav",
    )
    _s.add(_c23_ch)
    _s.commit()
    _s.refresh(_c23_ch)
    _c23_ch_id = _c23_ch.id

_c23_calls: list = []
books_module.generate_chapter_queue_pump = lambda: _c23_calls.append(1)

with TestClient(app) as _tc:
    _r23 = _tc.post(f"/books/{_c23_book_id}/chapters/1/generate")
    assert _r23.status_code == 202, f"Expected 202, got {_r23.status_code} ({_r23.text})"

books_module.generate_chapter_queue_pump = _generate_chapter_queue_pump_task  # restore

assert _c23_calls == [1], f"Expected pump dispatched once, got {_c23_calls}"
with Session(_c3c_engine) as _s:
    _c23_ch_after = _s.get(Chapter, _c23_ch_id)
    assert _c23_ch_after.queued_at is not None, "Expected queued_at to be set"
ok(f"202, re-dispatch accepted for DONE chapter (chapter_id={_c23_ch_id})")

# Section 23b (Phase 22) — 409 if chapter already GENERATING (no duplicate Huey dispatch)
section("POST /books/{id}/chapters/{n}/generate — 409 if chapter already GENERATING")

with Session(_c3c_engine) as _s:
    _c23b_book = Book(title="AlreadyGenBook", source_path="/tmp/zz.epub", status=BookStatus.ANALYZED)
    _s.add(_c23b_book)
    _s.commit()
    _s.refresh(_c23b_book)
    _c23b_book_id = _c23b_book.id

    _c23b_ch = Chapter(
        book_id=_c23b_book_id, position=1, raw_text="x",
        status=ChapterStatus.GENERATING,
    )
    _s.add(_c23b_ch)
    _s.commit()

_c23b_calls: list = []
books_module.generate_chapter_queue_pump = lambda: _c23b_calls.append(1)

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r23b = _tc.post(f"/books/{_c23b_book_id}/chapters/1/generate")
    assert _r23b.status_code == 409, f"Expected 409, got {_r23b.status_code} ({_r23b.text})"

books_module.generate_chapter_queue_pump = _generate_chapter_queue_pump_task  # restore

assert _c23b_calls == [], f"pump must NOT be dispatched, got {_c23b_calls}"
ok("409 si chapitre déjà GENERATING, pompe non dispatchée (pas de doublon Huey)")

app.dependency_overrides.clear()


# ── 24-26. Stale error_message cleared on successful retry ──────────────────
# Régression : un livre/chapitre FAILED puis relancé avec succès gardait l'ancien
# error_message en base (status terminal correct mais champ d'erreur stale).

# Section 24: _analyze_book_impl clears a pre-existing error_message on success
section("_analyze_book_impl: stale error_message cleared on successful retry")

_ea_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _ea_tmp:
    _ea_epub = Path(_ea_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _ea_epub)

    with Session(_ea_engine) as _s:
        _ea_book = Book(
            title="RetryAnalyze", source_path=str(_ea_epub),
            error_message="old analyze failure",
        )
        _s.add(_ea_book)
        _s.commit()
        _s.refresh(_ea_book)
        _ea_book_id = _ea_book.id

    with (
        patch("app.core.db.get_engine", return_value=_ea_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_make_mock_llm()),
    ):
        _analyze_book_impl(_ea_book_id)

    with Session(_ea_engine) as _s:
        _ea_b = _s.get(Book, _ea_book_id)
        if _ea_b.status == BookStatus.FAILED:
            die(f"_analyze_book_impl FAILED unexpectedly: {_ea_b.error_message!r}")
        assert _ea_b.status == BookStatus.ANALYZED, f"Expected ANALYZED, got {_ea_b.status}"
        assert _ea_b.error_message is None, (
            f"error_message must be cleared on success, got {_ea_b.error_message!r}"
        )
    ok("status=ANALYZED, error_message=None (stale message cleared)")


# Section 25: _generate_book_impl clears a pre-existing error_message on success
section("_generate_book_impl: stale error_message cleared on successful retry")

_eg_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _eg_tmp:
    _eg_epub = Path(_eg_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _eg_epub)
    _eg_book_id = _seed_analyzed_book(_eg_engine, str(_eg_epub))

    with Session(_eg_engine) as _s:
        _eg_b = _s.get(Book, _eg_book_id)
        _eg_b.error_message = "old generate failure"
        _s.add(_eg_b)
        _s.commit()

    with (
        patch("app.core.db.get_engine", return_value=_eg_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()),
    ):
        _generate_book_impl(_eg_book_id)

    with Session(_eg_engine) as _s:
        _eg_b = _s.get(Book, _eg_book_id)
        if _eg_b.status == BookStatus.FAILED:
            die(f"_generate_book_impl FAILED unexpectedly: {_eg_b.error_message!r}")
        assert _eg_b.status == BookStatus.DONE, f"Expected DONE, got {_eg_b.status}"
        assert _eg_b.error_message is None, (
            f"error_message must be cleared on success, got {_eg_b.error_message!r}"
        )
    ok("status=DONE, error_message=None (stale message cleared)")


# Section 26: _generate_chapter_impl clears a pre-existing error_message on success
section("_generate_chapter_impl: stale error_message cleared on successful retry")

_ec_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _ec_tmp:
    _ec_epub = Path(_ec_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _ec_epub)
    _ec_book_id = _seed_analyzed_book(_ec_engine, str(_ec_epub))
    _ec_ch_id = _get_chapter_id(_ec_engine, _ec_book_id)

    with Session(_ec_engine) as _s:
        _ec_ch = _s.get(Chapter, _ec_ch_id)
        _ec_ch.status = ChapterStatus.FAILED
        _ec_ch.error_message = "old chapter tts failure"
        _s.add(_ec_ch)
        _s.commit()

    with (
        patch("app.core.db.get_engine", return_value=_ec_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()),
    ):
        _generate_chapter_impl(_ec_ch_id)

    with Session(_ec_engine) as _s:
        _ec_ch = _s.get(Chapter, _ec_ch_id)
        if _ec_ch.status == ChapterStatus.FAILED:
            die(f"_generate_chapter_impl FAILED unexpectedly: {_ec_ch.error_message!r}")
        assert _ec_ch.status == ChapterStatus.DONE, f"Expected DONE, got {_ec_ch.status}"
        assert _ec_ch.error_message is None, (
            f"error_message must be cleared on success, got {_ec_ch.error_message!r}"
        )
    ok("status=DONE, error_message=None (stale message cleared)")


# ── 27-29. POST /books/{id}/chapters/generate — dispatch ALL chapters at once ──

_call_engine = _make_test_engine()


def _call_session():
    with Session(_call_engine) as _s:
        yield _s


app.dependency_overrides[get_session] = _call_session

# Section 27: 404 if book not found
section("POST /books/{id}/chapters/generate — 404 if book not found")

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r27 = _tc.post("/books/9999/chapters/generate")
    assert _r27.status_code == 404, f"Expected 404, got {_r27.status_code}"
ok("404 for non-existent book")

# Section 28: 409 if book status != ANALYZED
section("POST /books/{id}/chapters/generate — 409 if book status != ANALYZED")

with Session(_call_engine) as _s:
    _r28_book = Book(title="NotAnalyzed", source_path="/tmp/x.epub", status=BookStatus.PROCESSING)
    _s.add(_r28_book)
    _s.commit()
    _s.refresh(_r28_book)
    _r28_book_id = _r28_book.id

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r28 = _tc.post(f"/books/{_r28_book_id}/chapters/generate")
    assert _r28.status_code == 409, f"Expected 409, got {_r28.status_code}"
ok("409 for book status=PROCESSING")

# Section 29: happy path — dispatch only non-DONE chapters, skip the DONE one
section("POST /books/{id}/chapters/generate — dispatches only non-DONE chapters")

with Session(_call_engine) as _s:
    _r29_book = Book(title="AllChapters", source_path="/tmp/y.epub", status=BookStatus.ANALYZED)
    _s.add(_r29_book)
    _s.commit()
    _s.refresh(_r29_book)
    _r29_book_id = _r29_book.id

    _r29_ch1 = Chapter(book_id=_r29_book_id, position=1, raw_text="a", status=ChapterStatus.DONE, audio_path="/data/1/ch1.wav")
    _r29_ch2 = Chapter(book_id=_r29_book_id, position=2, raw_text="b", status=ChapterStatus.PENDING)
    _r29_ch3 = Chapter(book_id=_r29_book_id, position=3, raw_text="c", status=ChapterStatus.FAILED, error_message="boom")
    _r29_ch4 = Chapter(book_id=_r29_book_id, position=4, raw_text="d", status=ChapterStatus.GENERATING)
    _s.add(_r29_ch1)
    _s.add(_r29_ch2)
    _s.add(_r29_ch3)
    _s.add(_r29_ch4)
    _s.commit()
    _s.refresh(_r29_ch1)
    _s.refresh(_r29_ch2)
    _s.refresh(_r29_ch3)
    _s.refresh(_r29_ch4)
    _r29_ch1_id = _r29_ch1.id
    _r29_ch2_id, _r29_ch3_id = _r29_ch2.id, _r29_ch3.id
    _r29_ch4_id = _r29_ch4.id

_r29_calls: list = []
books_module.generate_chapter_queue_pump = lambda: _r29_calls.append(1)

with TestClient(app) as _tc:
    _r29 = _tc.post(f"/books/{_r29_book_id}/chapters/generate")
    assert _r29.status_code == 202, f"Expected 202, got {_r29.status_code} ({_r29.text})"
    _r29_data = _r29.json()
    assert len(_r29_data) == 4, f"Expected 4 chapters in response, got {len(_r29_data)}"

books_module.generate_chapter_queue_pump = _generate_chapter_queue_pump_task  # restore

assert _r29_calls == [1], (
    f"Expected pump dispatched exactly once (not per-chapter), got {_r29_calls}"
)
with Session(_call_engine) as _s:
    _r29_ch1_after = _s.get(Chapter, _r29_ch1_id)
    _r29_ch2_after = _s.get(Chapter, _r29_ch2_id)
    _r29_ch3_after = _s.get(Chapter, _r29_ch3_id)
    _r29_ch4_after = _s.get(Chapter, _r29_ch4_id)
    assert _r29_ch1_after.queued_at is None, "DONE chapter must not be queued"
    assert _r29_ch2_after.queued_at is not None, "PENDING chapter must be queued"
    assert _r29_ch3_after.queued_at is not None, "FAILED chapter must be queued"
    assert _r29_ch4_after.queued_at is None, "GENERATING chapter must not be re-queued"
ok(f"202, pompe dispatchée une fois, queued_at posé sur PENDING+FAILED uniquement (book_id={_r29_book_id})")

# ── Phase 17 — PATCH /books/{id}: provider TTS par livre ──────────────────────

app.dependency_overrides[get_session] = _rb_session

section("PATCH /books/{id}: tts_provider valide -> 200 + persisté")

with Session(_rb_engine) as _s30:
    _r30_book = Book(title="ProviderTest", source_path="/tmp/provider.epub")
    _s30.add(_r30_book)
    _s30.commit()
    _r30_book_id = _r30_book.id

with TestClient(app) as _tc:
    _r30 = _tc.patch(f"/books/{_r30_book_id}", json={"tts_provider": "qwen"})
    assert _r30.status_code == 200, f"Expected 200, got {_r30.status_code} ({_r30.text})"
    assert _r30.json()["tts_provider"] == "qwen", f"got {_r30.json()}"
ok("tts_provider='qwen' persisté et renvoyé dans BookResponse")

section("PATCH /books/{id}: tts_provider invalide -> 422")

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r31 = _tc.patch(f"/books/{_r30_book_id}", json={"tts_provider": "ghost_provider"})
    assert _r31.status_code == 422, f"Expected 422, got {_r31.status_code} ({_r31.text})"
ok("422 si tts_provider hors catalogue")

section("PATCH /books/{id}: livre inexistant -> 404")

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r32 = _tc.patch("/books/999999", json={"tts_provider": "edgetts"})
    assert _r32.status_code == 404, f"Expected 404, got {_r32.status_code} ({_r32.text})"
ok("404 si book_id inconnu")

# ── Phase 19 (suite) — PATCH /books/{id}: genre + mise à jour partielle ──────

section("PATCH /books/{id}: genre seul -> persisté, tts_provider inchangé (pas d'effacement croisé)")

with TestClient(app) as _tc:
    _r34 = _tc.patch(f"/books/{_r30_book_id}", json={"genre": "Fantasy"})
    assert _r34.status_code == 200, f"Expected 200, got {_r34.status_code} ({_r34.text})"
    _r34_data = _r34.json()
    assert _r34_data["genre"] == "Fantasy", f"got {_r34_data}"
    assert _r34_data["tts_provider"] == "qwen", (
        f"tts_provider (set in section 30) must survive a genre-only PATCH, got {_r34_data}"
    )
ok("genre='Fantasy' persisté, tts_provider='qwen' (section 30) toujours présent")

section("PATCH /books/{id}: tts_provider seul -> persisté, genre inchangé (pas d'effacement croisé)")

with TestClient(app) as _tc:
    _r35 = _tc.patch(f"/books/{_r30_book_id}", json={"tts_provider": "piper"})
    assert _r35.status_code == 200, f"Expected 200, got {_r35.status_code} ({_r35.text})"
    _r35_data = _r35.json()
    assert _r35_data["tts_provider"] == "piper", f"got {_r35_data}"
    assert _r35_data["genre"] == "Fantasy", (
        f"genre (set in section 34) must survive a tts_provider-only PATCH, got {_r35_data}"
    )
ok("tts_provider='piper' persisté, genre='Fantasy' (section 34) toujours présent")

section("PATCH /books/{id}: genre=null explicite -> efface le genre")

with TestClient(app) as _tc:
    _r36 = _tc.patch(f"/books/{_r30_book_id}", json={"genre": None})
    assert _r36.status_code == 200, f"Expected 200, got {_r36.status_code} ({_r36.text})"
    assert _r36.json()["genre"] is None, f"got {_r36.json()}"
ok("genre=None explicite efface bien le champ")

section("PATCH /books/{id}: language + published_at -> persistés sans effacer tts_provider")

with TestClient(app) as _tc:
    _r37 = _tc.patch(
        f"/books/{_r30_book_id}", json={"language": "fr", "published_at": "1997-06-26"}
    )
    assert _r37.status_code == 200, f"Expected 200, got {_r37.status_code} ({_r37.text})"
    _r37_data = _r37.json()
    assert _r37_data["language"] == "fr", f"got {_r37_data}"
    assert _r37_data["published_at"] == "1997-06-26", f"got {_r37_data}"
    assert _r37_data["tts_provider"] == "piper", (
        f"tts_provider (section 35) must survive, got {_r37_data}"
    )
ok("language='fr', published_at='1997-06-26' persistés, tts_provider toujours présent")

section("GET /settings: provider par défaut + liste des providers disponibles")

with TestClient(app) as _tc:
    _r33 = _tc.get("/settings")
    assert _r33.status_code == 200, f"Expected 200, got {_r33.status_code} ({_r33.text})"
    _r33_data = _r33.json()
    assert _r33_data["default_tts_provider"], f"got {_r33_data}"
    assert set(_r33_data["available_tts_providers"]) == {"piper", "edgetts", "qwen"}, (
        f"got {_r33_data['available_tts_providers']}"
    )
ok(f"GET /settings -> {_r33_data}")

section("GET /settings: preferred_tts_provider absent par défaut (null)")

with TestClient(app) as _tc:
    _r34 = _tc.get("/settings")
    assert _r34.status_code == 200, f"Expected 200, got {_r34.status_code} ({_r34.text})"
    assert _r34.json()["preferred_tts_provider"] is None, f"got {_r34.json()}"
ok("preferred_tts_provider == None avant tout PATCH")

section("PATCH /settings: persiste la préférence, rejette une valeur invalide")

with TestClient(app) as _tc:
    _r35 = _tc.patch("/settings", json={"preferred_tts_provider": "edgetts"})
    assert _r35.status_code == 200, f"Expected 200, got {_r35.status_code} ({_r35.text})"
    assert _r35.json()["preferred_tts_provider"] == "edgetts", f"got {_r35.json()}"

    _r36 = _tc.get("/settings")
    assert _r36.json()["preferred_tts_provider"] == "edgetts", (
        f"la préférence doit survivre à une nouvelle requête, got {_r36.json()}"
    )

    _r37b = _tc.patch("/settings", json={"preferred_tts_provider": "not_a_provider"})
    assert _r37b.status_code == 422, f"Expected 422, got {_r37b.status_code} ({_r37b.text})"

    _r38 = _tc.patch("/settings", json={"preferred_tts_provider": None})
    assert _r38.status_code == 200, f"Expected 200, got {_r38.status_code} ({_r38.text})"
    assert _r38.json()["preferred_tts_provider"] is None, f"got {_r38.json()}"
ok("PATCH persiste, 422 sur valeur invalide, remise à None supportée")

app.dependency_overrides.clear()


print("\nPHASE 7 (split worker + route + generate trigger + étapes 3a/3b/3c) OK\n")
