"""check_phase11.py — Phase 10 Etape 1: wav_to_mp3 + schemas mp3_path.

Verifie la conversion WAV->MP3 (lameenc) et l'exposition de mp3_path
dans Book (SQLModel) et BookResponse (Pydantic).
Run: .venv/Scripts/python tests/check_phase11.py
"""
import io
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p11.db",
    "HUEY_DB_PATH": "./huey_test_p11.db",
    "TTS_PROVIDER": "edgetts",
})

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
    msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
    print(msg)
    _errors.append(msg)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        ok(label)
    else:
        fail(label, detail)


def _make_wav(n_frames: int = 22050, framerate: int = 22050, sampwidth: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(b"\x00" * (n_frames * sampwidth))
    return buf.getvalue()


# ── 1. wav_to_mp3 -- happy path ───────────────────────────────────────────────
section("wav_to_mp3 -- WAV 22050Hz mono 16bit => MP3 non vide")
from app.services.audio.assembler import wav_to_mp3  # noqa: E402

wav = _make_wav()
try:
    mp3 = wav_to_mp3(wav)
    check("retourne des bytes", isinstance(mp3, bytes))
    check("mp3 non vide", len(mp3) > 0)
    # MP3 frames start with sync byte 0xFF
    check("premier octet = 0xFF (sync MP3)", mp3[0] == 0xFF, f"got 0x{mp3[0]:02X}")
    ok(f"taille MP3 = {len(mp3)} octets pour WAV de {len(wav)} octets")
except Exception as exc:
    fail("wav_to_mp3 a leve une exception", str(exc))


# ── 2. wav_to_mp3 -- WAV 8-bit => ValueError ─────────────────────────────────
section("wav_to_mp3 -- WAV 8-bit => ValueError (sampwidth != 2)")
wav_8bit = _make_wav(sampwidth=1)
try:
    wav_to_mp3(wav_8bit)
    fail("ValueError non levee pour WAV 8-bit")
except ValueError as exc:
    check("ValueError levee", True)
    check("message mentionne sampwidth", "sampwidth" in str(exc), str(exc))
except Exception as exc:
    fail("mauvaise exception", str(exc))


# ── 3. wav_to_mp3 -- WAV vide (0 frames) => ValueError ───────────────────────
section("wav_to_mp3 -- WAV 0 frames => ValueError")
wav_empty = _make_wav(n_frames=0)
try:
    wav_to_mp3(wav_empty)
    fail("ValueError non levee pour WAV sans frames")
except ValueError as exc:
    check("ValueError levee", True)
    check("message mentionne frames", "frame" in str(exc).lower(), str(exc))
except Exception as exc:
    fail("mauvaise exception", str(exc))


# ── 4. wav_to_mp3 -- bytes invalides => exception ────────────────────────────
section("wav_to_mp3 -- bytes non-WAV => exception")
try:
    wav_to_mp3(b"NOT A WAV FILE")
    fail("exception non levee pour bytes invalides")
except Exception:
    check("exception levee sur bytes invalides", True)


# ── 5. Book.mp3_path -- colonne SQLModel ─────────────────────────────────────
section("Book SQLModel -- mp3_path (Optional[str] = None)")
from app.models.entities import Book  # noqa: E402

b = Book(title="Test MP3", source_path="test.epub")
check("mp3_path par defaut = None", b.mp3_path is None)
b.mp3_path = "data/1/book.mp3"
check("mp3_path assignable", b.mp3_path == "data/1/book.mp3")


# ── 6. BookResponse.mp3_path -- schema Pydantic ───────────────────────────────
section("BookResponse -- mp3_path (Optional[str] = None)")
from app.schemas.book import BookResponse  # noqa: E402
from app.core.enums import BookStatus  # noqa: E402

r = BookResponse(
    id=1, title="Test", status=BookStatus.PENDING,
    progress=0.0, created_at=datetime.now(timezone.utc),
)
check("mp3_path absent => None par defaut", r.mp3_path is None)

r2 = BookResponse(
    id=2, title="Test2", status=BookStatus.DONE,
    progress=100.0, created_at=datetime.now(timezone.utc),
    mp3_path="data/2/book.mp3",
)
check("mp3_path renseignable", r2.mp3_path == "data/2/book.mp3")


# ── Resume ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
