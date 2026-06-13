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


# ── 5. Stubs lèvent NotImplementedError ───────────────────────────────────────
section("PiperProvider.synthesise raises NotImplementedError")
get_settings.cache_clear()
piper = PiperProvider(get_settings())
try:
    asyncio.run(piper.synthesise("hello", "voice_id"))
    die("Expected NotImplementedError from PiperProvider")
except NotImplementedError:
    ok("NotImplementedError raised as expected")

section("ElevenLabsProvider.synthesise raises NotImplementedError")
os.environ["TTS_PROVIDER"] = "elevenlabs"
os.environ["ELEVENLABS_API_KEY"] = "fake-key"
get_settings.cache_clear()
el = ElevenLabsProvider(get_settings())
try:
    asyncio.run(el.synthesise("hello", "voice_id"))
    die("Expected NotImplementedError from ElevenLabsProvider")
except NotImplementedError:
    ok("NotImplementedError raised as expected")

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


print("\nPHASE 4 (scaffold + voice assignment + config) OK\n")
