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


print("\nPHASE 4 (scaffold) OK\n")
