"""Phase 4 verification — TTS scaffold (Strategy pattern stubs).
Run: .venv/Scripts/python tests/check_phase4.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p4.db",
    "HUEY_DB_PATH": "./huey_test_p4.db",
    "PIPER_VOICES_DIR": "./voices",
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


# ── 1. Imports ────────────────────────────────────────────────────────────────
section("All TTS modules import cleanly")
from app.services.tts.base import BaseTTSProvider  # noqa: E402
from app.services.tts.piper import PiperProvider  # noqa: E402
from app.services.tts.elevenlabs import ElevenLabsProvider  # noqa: E402
from app.services.tts.factory import get_tts_provider  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402
ok("base, piper, elevenlabs, factory, TTSError")


# ── 2. BaseTTSProvider is abstract ────────────────────────────────────────────
section("BaseTTSProvider cannot be instantiated")
try:
    BaseTTSProvider()  # type: ignore[abstract]
    die("Expected TypeError — BaseTTSProvider should be abstract")
except TypeError:
    ok("TypeError raised as expected")


# ── 3. Factory returns correct types ─────────────────────────────────────────
section("get_tts_provider() returns correct concrete class")
from app.config import get_settings  # noqa: E402
get_settings.cache_clear()
settings = get_settings()
provider = get_tts_provider(settings)
assert isinstance(provider, PiperProvider), f"Expected PiperProvider, got {type(provider)}"
ok(f"TTS_PROVIDER=piper => {type(provider).__name__}")

os.environ["TTS_PROVIDER"] = "elevenlabs"
os.environ["ELEVENLABS_API_KEY"] = "fake-key-for-type-check"
get_settings.cache_clear()
el_provider = get_tts_provider(get_settings())
assert isinstance(el_provider, ElevenLabsProvider), f"Expected ElevenLabsProvider, got {type(el_provider)}"
ok(f"TTS_PROVIDER=elevenlabs => {type(el_provider).__name__}")

# Restore to piper for remaining tests
os.environ["TTS_PROVIDER"] = "piper"
del os.environ["ELEVENLABS_API_KEY"]
get_settings.cache_clear()


# ── 4. Fail-fast: ELEVENLABS_API_KEY manquant ─────────────────────────────────
section("Settings raises ValueError when ELEVENLABS_API_KEY is absent")
os.environ["TTS_PROVIDER"] = "elevenlabs"
os.environ.pop("ELEVENLABS_API_KEY", None)
get_settings.cache_clear()
try:
    get_settings()
    die("Expected ValueError when ELEVENLABS_API_KEY missing")
except ValueError as exc:
    assert "ELEVENLABS_API_KEY" in str(exc), f"Unexpected error: {exc}"
    ok(f"ValueError raised: {exc}")
finally:
    os.environ["TTS_PROVIDER"] = "piper"
    get_settings.cache_clear()


# ── 5. PiperProvider lève TTSError (model absent / piper-tts non installé) ───
section("PiperProvider.synthesise raises TTSError when model unavailable")
get_settings.cache_clear()
piper = PiperProvider(get_settings())
try:
    asyncio.run(piper.synthesise("hello", "nonexistent_voice"))
    die("Expected TTSError from PiperProvider")
except TTSError:
    ok("TTSError raised (missing model file or piper-tts not installed)")

# ── 6. ElevenLabsProvider lève TTSError sur erreur HTTP ──────────────────────
section("ElevenLabsProvider.synthesise raises TTSError on HTTP error")
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402
import httpx  # noqa: E402

os.environ["TTS_PROVIDER"] = "elevenlabs"
os.environ["ELEVENLABS_API_KEY"] = "fake-key"
get_settings.cache_clear()
el = ElevenLabsProvider(get_settings())

with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
           side_effect=httpx.ConnectError("connection refused")):
    try:
        asyncio.run(el.synthesise("hello", "voice_id"))
        die("Expected TTSError from ElevenLabsProvider")
    except TTSError:
        ok("TTSError raised on HTTP ConnectError")

os.environ["TTS_PROVIDER"] = "piper"
del os.environ["ELEVENLABS_API_KEY"]
get_settings.cache_clear()


# ── 6. TTSError stocke context et cause ───────────────────────────────────────
section("TTSError stores context and cause correctly")
cause = RuntimeError("synthesis failed")
err = TTSError("piper:voice_01", cause)
assert err.context == "piper:voice_01"
assert err.cause is cause
assert "piper:voice_01" in str(err)
ok(f"TTSError: {err}")



# ── 7. Import voice_assignment ────────────────────────────────────────────────
section("voice_assignment module imports cleanly")
from app.services.voice_assignment import (  # noqa: E402
    NARRATOR_VOICE_ID,
    VOICE_CATALOGUE,
    assign_voices,
)
ok("NARRATOR_VOICE_ID, VOICE_CATALOGUE, assign_voices imported")


# ── 8. NARRATOR_VOICE_ID ─────────────────────────────────────────────────────
section("NARRATOR_VOICE_ID is a non-empty string")
assert isinstance(NARRATOR_VOICE_ID, str) and NARRATOR_VOICE_ID, \
    "NARRATOR_VOICE_ID must be a non-empty string"
ok(f"NARRATOR_VOICE_ID = {NARRATOR_VOICE_ID!r}")


# ── 9. VOICE_CATALOGUE covers all Gender values ───────────────────────────────
section("VOICE_CATALOGUE covers all Gender values with non-empty pools")
from app.core.enums import Gender  # noqa: E402
for _g in Gender:
    assert _g in VOICE_CATALOGUE, f"Missing gender {_g} in VOICE_CATALOGUE"
    assert len(VOICE_CATALOGUE[_g]) >= 1, f"Empty pool for {_g}"
ok(f"All genders covered — pools: { {g.value: len(v) for g, v in VOICE_CATALOGUE.items()} }")


# ── 10. assign_voices populates Character.voice_id ───────────────────────────
section("assign_voices() populates voice_id for all characters of a book")
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from app.models.entities import Book, Character  # noqa: E402

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(_engine)

with Session(_engine) as _s:
    _book = Book(title="Test Book", source_path="/tmp/test.epub")
    _s.add(_book)
    _s.commit()
    _s.refresh(_book)

    _alice = Character(book_id=_book.id, name="Alice", gender=Gender.FEMALE)
    _bob   = Character(book_id=_book.id, name="Bob",   gender=Gender.MALE)
    _zara  = Character(book_id=_book.id, name="Zara",  gender=Gender.UNKNOWN)
    for _c in (_alice, _bob, _zara):
        _s.add(_c)
    _s.commit()

    assign_voices(_book.id, _s)

    for _c in (_alice, _bob, _zara):
        _s.refresh(_c)
        assert _c.voice_id is not None, f"{_c.name} has no voice_id after assign_voices()"
        ok(f"{_c.name} ({_c.gender.value}) => {_c.voice_id!r}")

    _book_id = _book.id


# ── 11. assign_voices is idempotent ──────────────────────────────────────────
section("assign_voices() is idempotent — re-run preserves existing voice_ids")
with Session(_engine) as _s:
    _before = {
        _c.name: _c.voice_id
        for _c in _s.exec(select(Character).where(Character.book_id == _book_id)).all()
    }
    assign_voices(_book_id, _s)
    _after = {
        _c.name: _c.voice_id
        for _c in _s.exec(select(Character).where(Character.book_id == _book_id)).all()
    }
    assert _before == _after, f"voice_ids changed on second call: {_before} vs {_after}"
    ok(f"Stable after two calls: {_after}")


# ── 12. Gender-based pool assignment ─────────────────────────────────────────
section("Male characters receive male_* voices; female characters female_* voices")
with Session(_engine) as _s:
    _a = _s.exec(select(Character).where(Character.name == "Alice")).one()
    _b = _s.exec(select(Character).where(Character.name == "Bob")).one()
    assert _a.voice_id in VOICE_CATALOGUE[Gender.FEMALE], \
        f"Alice should be in female pool, got {_a.voice_id!r}"
    assert _b.voice_id in VOICE_CATALOGUE[Gender.MALE], \
        f"Bob should be in male pool, got {_b.voice_id!r}"
    ok(f"Alice => {_a.voice_id!r} (female pool), Bob => {_b.voice_id!r} (male pool)")


# ── 13. Round-robin wraps within a pool ──────────────────────────────────────
section("Round-robin wraps when character count exceeds pool size")
with Session(_engine) as _s:
    _book2 = Book(title="Big Cast", source_path="/tmp/big.epub")
    _s.add(_book2)
    _s.commit()
    _s.refresh(_book2)

    _pool = VOICE_CATALOGUE[Gender.MALE]
    _many = [
        Character(book_id=_book2.id, name=f"Man_{i:02d}", gender=Gender.MALE)
        for i in range(len(_pool) + 1)
    ]
    for _c in _many:
        _s.add(_c)
    _s.commit()

    assign_voices(_book2.id, _s)
    for _c in _many:
        _s.refresh(_c)

    _voices = [_c.voice_id for _c in _many]
    assert _voices[0] == _voices[len(_pool)], (
        f"Expected wrap-around: voices[0]={_voices[0]!r} should equal "
        f"voices[{len(_pool)}]={_voices[len(_pool)]!r}"
    )
    ok(f"Round-robin confirmed: {_voices}")



# ── 15. Fail-fast: PIPER_VOICES_DIR manquant ─────────────────────────────────
section("Settings raises ValueError when PIPER_VOICES_DIR absent with TTS_PROVIDER=piper")
os.environ["TTS_PROVIDER"] = "piper"
os.environ.pop("PIPER_VOICES_DIR", None)
get_settings.cache_clear()
try:
    get_settings()
    die("Expected ValueError when PIPER_VOICES_DIR is missing")
except ValueError as exc:
    assert "PIPER_VOICES_DIR" in str(exc), f"Unexpected error: {exc}"
    ok(f"ValueError raised: {exc}")
finally:
    os.environ["PIPER_VOICES_DIR"] = "./voices"
    get_settings.cache_clear()



# ── 16. Import assembler ──────────────────────────────────────────────────────
section("audio.assembler module imports cleanly")
from app.services.audio.assembler import assemble_wav  # noqa: E402
ok("assemble_wav imported")


# ── 17. Book.audio_path field exists ─────────────────────────────────────────
section("Book model has audio_path: Optional[str] = None")
_bk = Book(title="t", source_path="/p")
assert _bk.audio_path is None, f"audio_path default must be None, got {_bk.audio_path!r}"
ok("Book.audio_path present, default=None")


# ── 18. assemble_wav raises ValueError on empty input ────────────────────────
section("assemble_wav() raises ValueError on empty segment list")
import tempfile  # noqa: E402
try:
    assemble_wav([], "/tmp/out.wav")
    die("Expected ValueError on empty segment list")
except ValueError as exc:
    ok(f"ValueError raised: {exc}")


# ── 19. assemble_wav concatenates WAV segments correctly ─────────────────────
section("assemble_wav() produces valid WAV with correct total frame count")
import io    # noqa: E402
import wave  # noqa: E402


def _make_wav_bytes(n_frames: int, framerate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as _w:
        _w.setnchannels(1)
        _w.setsampwidth(2)
        _w.setframerate(framerate)
        _w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


_seg1, _seg2, _seg3 = _make_wav_bytes(100), _make_wav_bytes(200), _make_wav_bytes(50)

with tempfile.TemporaryDirectory() as _tmpdir:
    _out = assemble_wav([_seg1, _seg2, _seg3], Path(_tmpdir) / "out.wav")
    assert _out.exists(), f"Output file not created: {_out}"
    with wave.open(str(_out), "rb") as _assembled:
        assert _assembled.getnframes() == 350, \
            f"Expected 350 frames, got {_assembled.getnframes()}"
        assert _assembled.getnchannels() == 1
        assert _assembled.getframerate() == 22050
    ok("Assembled WAV: 3 segments -> 350 frames, 1ch / 22050 Hz")



# ── 20. ElevenLabsProvider retourne du WAV valide sur 200 ────────────────────
section("ElevenLabsProvider wraps PCM in valid WAV bytes on HTTP 200")
os.environ["TTS_PROVIDER"] = "elevenlabs"
os.environ["ELEVENLABS_API_KEY"] = "fake-key"
get_settings.cache_clear()
_el_ok = ElevenLabsProvider(get_settings())

_fake_pcm = b"\x00\x00" * 100  # 100 frames, 16-bit silence
_mock_resp = MagicMock()
_mock_resp.raise_for_status.return_value = None
_mock_resp.content = _fake_pcm

with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_resp):
    _wav = asyncio.run(_el_ok.synthesise("hello world", "test_voice_id"))
    assert _wav[:4] == b"RIFF", f"Expected WAV RIFF header, got {_wav[:4]!r}"
    with wave.open(io.BytesIO(_wav), "rb") as _wf:
        assert _wf.getnframes() == 100, f"Expected 100 frames, got {_wf.getnframes()}"
    ok(f"ElevenLabsProvider returned {len(_wav)}-byte WAV from 200-byte PCM input")

os.environ["TTS_PROVIDER"] = "piper"
del os.environ["ELEVENLABS_API_KEY"]
get_settings.cache_clear()



# ── 21. _synthesise_book crée le fichier audio et retourne le chemin ──────────
section("_synthesise_book() synthesises all segments and assembles WAV")
from app.workers.tasks import _synthesise_book  # noqa: E402
from app.models.entities import Chapter, Segment  # noqa: E402
from app.core.enums import SegmentType  # noqa: E402

_s21_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(_s21_engine)


async def _s21_fake_tts(text: str, voice_id: str) -> bytes:
    return _make_wav_bytes(50)


_s21_mock_tts = MagicMock()
_s21_mock_tts.synthesise = AsyncMock(side_effect=_s21_fake_tts)

with tempfile.TemporaryDirectory() as _s21_tmp:
    _s21_epub = str(Path(_s21_tmp) / "book.epub")
    Path(_s21_epub).touch()

    with Session(_s21_engine) as _s21_s:
        _s21_book = Book(title="TTS Book", source_path=_s21_epub)
        _s21_s.add(_s21_book)
        _s21_s.commit()
        _s21_s.refresh(_s21_book)
        _s21_book_id = _s21_book.id

        _s21_ch = Chapter(book_id=_s21_book_id, position=1, title="Ch1", raw_text="x")
        _s21_s.add(_s21_ch)
        _s21_s.commit()
        _s21_s.refresh(_s21_ch)
        _s21_ch_id = _s21_ch.id

        _s21_char = Character(book_id=_s21_book_id, name="Alice", gender=Gender.FEMALE, voice_id="female_0")
        _s21_s.add(_s21_char)
        _s21_s.commit()
        _s21_s.refresh(_s21_char)
        _s21_char_id = _s21_char.id

        _s21_s.add(Segment(chapter_id=_s21_ch_id, position=1, text="Once.", segment_type=SegmentType.NARRATION))
        _s21_s.add(Segment(chapter_id=_s21_ch_id, position=2, text="Hello!", segment_type=SegmentType.DIALOGUE, character_id=_s21_char_id))
        _s21_s.commit()

    with patch("app.services.tts.factory.get_tts_provider", return_value=_s21_mock_tts):
        _s21_audio = asyncio.run(_synthesise_book(_s21_book_id, _s21_epub, _s21_engine))

    _s21_expected = str(Path(_s21_epub).with_suffix(".wav"))
    assert _s21_audio == _s21_expected, f"Expected {_s21_expected!r}, got {_s21_audio!r}"
    assert Path(_s21_audio).exists(), f"Audio file not created: {_s21_audio}"
    with wave.open(_s21_audio, "rb") as _s21_wf:
        assert _s21_wf.getnframes() == 100, f"Expected 100 frames (2x50), got {_s21_wf.getnframes()}"
    ok("_synthesise_book: 2 segments x 50 frames -> 100-frame WAV created")


# ── 22. audio_path dans BookResponse ─────────────────────────────────────────
section("BookResponse includes audio_path field")
from app.schemas.book import BookResponse  # noqa: E402
_br_fields = BookResponse.model_fields
assert "audio_path" in _br_fields, "audio_path missing from BookResponse"
assert _br_fields["audio_path"].default is None, "audio_path default must be None"
ok("BookResponse.audio_path present, default=None")


# ── 23. GET /books/{id}/audio — comportement 404 / 200 ───────────────────────
section("GET /books/{id}/audio — 404 when missing / 200 with WAV")
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import get_session  # noqa: E402

from sqlalchemy.pool import StaticPool  # noqa: E402
_s23_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(_s23_engine)


def _s23_override():
    with Session(_s23_engine) as s:
        yield s


app.dependency_overrides[get_session] = _s23_override

with TestClient(app, raise_server_exceptions=False) as _tc:
    # 404 — book inexistant
    _r = _tc.get("/books/9999/audio")
    assert _r.status_code == 404, f"Expected 404, got {_r.status_code}"
    ok("404 when book_id not found")

    # 404 — audio_path non renseigné
    with Session(_s23_engine) as _s23_s:
        _s23_book = Book(title="No Audio", source_path="/tmp/x.epub")
        _s23_s.add(_s23_book)
        _s23_s.commit()
        _s23_s.refresh(_s23_book)
        _s23_bid = _s23_book.id
    _r = _tc.get(f"/books/{_s23_bid}/audio")
    assert _r.status_code == 404, f"Expected 404, got {_r.status_code}"
    ok("404 when audio_path is None")

    # 200 — audio_path pointe vers un vrai fichier WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as _wav_f:
        _wav_f.write(_make_wav_bytes(10))
        _wav_path = _wav_f.name
    with Session(_s23_engine) as _s23_s:
        _s23_book2 = Book(title="Has Audio", source_path="/tmp/y.epub", audio_path=_wav_path)
        _s23_s.add(_s23_book2)
        _s23_s.commit()
        _s23_s.refresh(_s23_book2)
        _s23_bid2 = _s23_book2.id
    _r = _tc.get(f"/books/{_s23_bid2}/audio")
    assert _r.status_code == 200, f"Expected 200, got {_r.status_code}"
    assert "audio" in _r.headers.get("content-type", ""), \
        f"Expected audio content-type, got {_r.headers.get('content-type')}"
    ok(f"200 with content-type={_r.headers['content-type']!r}")

app.dependency_overrides.clear()


# ── 24. Fail-fast: PIPER_VOICES_DIR pointe vers un chemin inexistant ──────────
section("Settings raises ValueError when PIPER_VOICES_DIR is not an existing directory")
os.environ["TTS_PROVIDER"] = "piper"
os.environ["PIPER_VOICES_DIR"] = "./nonexistent_voices_xyz"
get_settings.cache_clear()
try:
    get_settings()
    die("Expected ValueError when PIPER_VOICES_DIR does not exist")
except ValueError as exc:
    assert "PIPER_VOICES_DIR" in str(exc), f"Unexpected error: {exc}"
    ok(f"ValueError raised: {exc}")
finally:
    os.environ["PIPER_VOICES_DIR"] = "./voices"
    get_settings.cache_clear()


# ── 25. Pas d'erreur quand PIPER_VOICES_DIR pointe vers ./voices (existant) ───
section("Settings accepts PIPER_VOICES_DIR when directory exists")
os.environ["TTS_PROVIDER"] = "piper"
os.environ["PIPER_VOICES_DIR"] = "./voices"
get_settings.cache_clear()
try:
    _s25 = get_settings()
    assert _s25.piper_voices_dir == "./voices"
    ok(f"No error — piper_voices_dir={_s25.piper_voices_dir!r}")
except ValueError as exc:
    die(f"Unexpected ValueError: {exc}")
finally:
    get_settings.cache_clear()


# ── 26. assemble_wav lève ValueError sur mismatch de format WAV ───────────────
section("assemble_wav() raises ValueError when WAV segments have mismatched formats")
_mis1 = _make_wav_bytes(100, framerate=22050)
_mis2 = _make_wav_bytes(100, framerate=16000)

with tempfile.TemporaryDirectory() as _mis_tmp:
    try:
        assemble_wav([_mis1, _mis2], Path(_mis_tmp) / "bad.wav")
        die("Expected ValueError on framerate mismatch")
    except ValueError as exc:
        assert "mismatch" in str(exc).lower(), f"Unexpected error text: {exc}"
        ok(f"ValueError raised: {exc}")


print("\nPHASE 4 (TTS implementations) OK\n")
