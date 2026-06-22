"""check_phase8.py — D1a: EdgeTTS scaffold (config, factory, voice mapping).
Run: .venv/Scripts/python tests/check_phase8.py
"""
import array as _array
import asyncio
import io
import os
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Set env before any app import (no piper vars needed for edgetts).
os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p8.db",
    "HUEY_DB_PATH": "./huey_test_p8.db",
    "TTS_PROVIDER": "edgetts",
})
os.environ.pop("EDGETTS_LOCALE", None)

PASS = "\033[32mOK\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_errors: list[str] = []
_n = 0


def section(title: str) -> None:
    global _n
    _n += 1
    print(f"\n[{_n}] {title}")


def ok(label: str) -> None:
    print(f"    ok  {label}")


def fail(label: str, detail: str = "") -> None:
    msg = f"    FAIL  {label}" + (f" — {detail}" if detail else "")
    print(msg)
    _errors.append(msg)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        ok(label)
    else:
        fail(label, detail)


def _raises(exc_type, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
        return False
    except exc_type:
        return True
    except Exception:
        return False


# ── Section 1: config accepte TTS_PROVIDER=edgetts ───────────────────────────

section("Config: TTS_PROVIDER=edgetts accepté, edgetts_locale='en-US' par défaut")

from app.config import Settings

try:
    s = Settings()
    check("Settings() sans exception", True)
    check("tts_provider == 'edgetts'", s.tts_provider == "edgetts")
    check("edgetts_locale == 'en-US'", s.edgetts_locale == "en-US")
except Exception as e:
    check("Settings() sans exception", False, str(e))
    check("tts_provider == 'edgetts'", False, "exception levée")
    check("edgetts_locale == 'en-US'", False, "exception levée")

# ── Section 2: EDGETTS_LOCALE custom ─────────────────────────────────────────

section("Config: EDGETTS_LOCALE=fr-FR stocké")

os.environ["EDGETTS_LOCALE"] = "fr-FR"
try:
    s2 = Settings()
    check("edgetts_locale == 'fr-FR'", s2.edgetts_locale == "fr-FR")
except Exception as e:
    check("edgetts_locale == 'fr-FR'", False, str(e))
finally:
    os.environ.pop("EDGETTS_LOCALE", None)

# ── Section 3: factory -> EdgeTTSProvider ─────────────────────────────────────

section("Factory: get_tts_provider('edgetts') -> EdgeTTSProvider")

from app.services.tts.edgetts import EdgeTTSProvider, _OUTPUT_SAMPLE_RATE
from app.services.tts.factory import get_tts_provider
import app.services.tts.edgetts as _edgetts_mod

mock_s = MagicMock()
mock_s.tts_provider = "edgetts"
mock_s.edgetts_locale = "en-US"

provider = get_tts_provider(mock_s)
check("isinstance EdgeTTSProvider", isinstance(provider, EdgeTTSProvider))

# ── Section 4: mapping en-US — tous les ids logiques ─────────────────────────

section("Mapping en-US: tous les ids du catalogue résolus vers voix Neural")

from app.services.voice_assignment import NARRATOR_VOICE_ID, VOICE_CATALOGUE

mock_en = MagicMock()
mock_en.edgetts_locale = "en-US"
p_en = EdgeTTSProvider(mock_en)

_seen: set[str] = set()
all_ids: list[str] = [NARRATOR_VOICE_ID]
_seen.add(NARRATOR_VOICE_ID)
for voices in VOICE_CATALOGUE.values():
    for v in voices:
        if v not in _seen:
            all_ids.append(v)
            _seen.add(v)

for vid in all_ids:
    try:
        edge_name = p_en.resolve_voice(vid)
        check(
            f"'{vid}' -> '{edge_name}'",
            bool(edge_name) and "Neural" in edge_name,
        )
    except Exception as e:
        fail(f"'{vid}' résolu", str(e))

# ── Section 5: mapping fr-FR — tous les ids logiques ─────────────────────────

section("Mapping fr-FR: tous les ids du catalogue résolus vers voix Neural")

mock_fr = MagicMock()
mock_fr.edgetts_locale = "fr-FR"
p_fr = EdgeTTSProvider(mock_fr)

for vid in all_ids:
    try:
        edge_name = p_fr.resolve_voice(vid)
        check(
            f"'{vid}' -> '{edge_name}'",
            bool(edge_name) and "Neural" in edge_name,
        )
    except Exception as e:
        fail(f"'{vid}' résolu", str(e))

# ── Section 6: voice_id inconnu -> TTSError ───────────────────────────────────

section("Mapping: voice_id inconnu -> TTSError")

from app.core.exceptions import TTSError

check(
    "resolve_voice('ghost_99') -> TTSError",
    _raises(TTSError, p_en.resolve_voice, "ghost_99"),
)

# ── Section 7: voice_id inconnu dans synthesise -> TTSError (offline) ────────

section("synthesise: voice_id inconnu -> TTSError offline (via resolve_voice)")

check(
    "synthesise('inconnu_99') -> TTSError",
    _raises(TTSError, asyncio.run, p_en.synthesise("hello", "inconnu_99")),
)

# ── Section 8: _pcm_to_wav helper (offline) ──────────────────────────────────

section("_pcm_to_wav: PCM brut -> WAV valide (stdlib, offline)")

from app.services.tts.edgetts import _pcm_to_wav

_silent_pcm = b"\x00\x00" * 1000  # 1000 frames 16-bit silence
_wav_bytes = _pcm_to_wav(_silent_pcm, _OUTPUT_SAMPLE_RATE)

try:
    with wave.open(io.BytesIO(_wav_bytes), "rb") as _w:
        check("nchannels == 1", _w.getnchannels() == 1)
        check("sampwidth == 2 (16-bit)", _w.getsampwidth() == 2)
        check(f"framerate == {_OUTPUT_SAMPLE_RATE}", _w.getframerate() == _OUTPUT_SAMPLE_RATE)
        check("nframes == 1000", _w.getnframes() == 1000)
except Exception as e:
    check("WAV parseable", False, str(e))

# ── Section 9: TTSError si edge_tts.stream() leve ────────────────────────────

section("synthesise: TTSError si edge_tts.stream() leve une exception")

async def _failing_stream():
    raise ConnectionError("réseau inaccessible")
    yield  # rend cette fonction un générateur asynchrone

async def _call_stream_fail():
    mock_comm = MagicMock()
    mock_comm.stream.return_value = _failing_stream()
    with patch.object(_edgetts_mod.edge_tts, "Communicate", return_value=mock_comm):
        return await p_en.synthesise("bonjour", "narrator")

check(
    "synthesise -> TTSError sur erreur réseau",
    _raises(TTSError, asyncio.run, _call_stream_fail()),
)

# ── Section 10: TTSError si miniaudio.decode leve ────────────────────────────

section("synthesise: TTSError si miniaudio.decode() echoue")

async def _audio_chunk_stream():
    yield {"type": "audio", "data": b"\x00" * 100}

async def _call_decode_fail():
    mock_comm = MagicMock()
    mock_comm.stream.return_value = _audio_chunk_stream()
    with patch.object(_edgetts_mod.edge_tts, "Communicate", return_value=mock_comm), \
         patch.object(_edgetts_mod.miniaudio, "decode", side_effect=Exception("MP3 corrompu")):
        return await p_en.synthesise("bonjour", "narrator")

check(
    "synthesise -> TTSError sur decode MP3 echoue",
    _raises(TTSError, asyncio.run, _call_decode_fail()),
)

# ── Section 11: happy path complet (edge_tts + miniaudio mockes) ──────────────

section("synthesise: WAV valide retourne (edge_tts + miniaudio mockes)")

class _FakeDecoded:
    def __init__(self) -> None:
        self.samples = _array.array("h", [0] * 1000)
        self.sample_rate = _OUTPUT_SAMPLE_RATE
        self.nchannels = 1

async def _success_stream():
    yield {"type": "audio", "data": b"\x00" * 10}

async def _call_success():
    mock_comm = MagicMock()
    mock_comm.stream.return_value = _success_stream()
    with patch.object(_edgetts_mod.edge_tts, "Communicate", return_value=mock_comm), \
         patch.object(_edgetts_mod.miniaudio, "decode", return_value=_FakeDecoded()):
        return await p_en.synthesise("hello", "narrator")

try:
    _wav_out = asyncio.run(_call_success())
    with wave.open(io.BytesIO(_wav_out), "rb") as _w:
        check("WAV valide retourne", True)
        check(f"framerate == {_OUTPUT_SAMPLE_RATE}", _w.getframerate() == _OUTPUT_SAMPLE_RATE)
        check("nchannels == 1", _w.getnchannels() == 1)
        check("nframes == 1000", _w.getnframes() == 1000)
except Exception as e:
    check("WAV valide retourne", False, str(e))


# ── Section 12 (B2) : emotion fournie -> no-op (EdgeTTS l'ignore), pas de crash ─

section("synthesise(..., emotion=...) -> WAV valide, no-op (EdgeTTS ignore emotion)")

async def _call_success_emotion():
    mock_comm = MagicMock()
    mock_comm.stream.return_value = _success_stream()
    with patch.object(_edgetts_mod.edge_tts, "Communicate", return_value=mock_comm), \
         patch.object(_edgetts_mod.miniaudio, "decode", return_value=_FakeDecoded()):
        return await p_en.synthesise("hello", "narrator", emotion="furious")

try:
    _wav_emo = asyncio.run(_call_success_emotion())
    check("emotion fournie -> WAV RIFF valide (no-op)", _wav_emo[:4] == b"RIFF")
except Exception as e:
    check("emotion fournie -> WAV RIFF valide (no-op)", False, str(e))

# ── Rapport ───────────────────────────────────────────────────────────────────

print(f"\n{'='*52}")
if _errors:
    print(f"FAIL — {len(_errors)} erreur(s) :")
    for e in _errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"OK — Toutes les sections passent (D1a scaffold).")
