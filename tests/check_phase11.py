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


# ── 7. Worker -- mp3_path ecrit apres generation ─────────────────────────────
# Réécrit (audit 2026-07-02, Lot C1) : _synthesise_book n'existe plus (génération
# livre unifiée sur le chemin chapitre) -- le patch global de asyncio.run ne
# fonctionne plus. On construit un vrai chapitre/segment et on laisse
# _generate_book_impl faire tout le travail normalement (mock uniquement au niveau
# du provider TTS), comme le reste de la suite Lot C (check_phase27.py).
section("Worker _generate_book_impl -- mp3_path persiste en BDD")
import tempfile as _tf  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402
from sqlalchemy import StaticPool, create_engine  # noqa: E402
from sqlmodel import SQLModel, Session as _Session, select as _select  # noqa: E402
from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.models.entities import Book, Chapter, Segment  # noqa: E402

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
SQLModel.metadata.create_all(_engine)

with _tf.TemporaryDirectory() as _tmpdir:
    _tmpdir = Path(_tmpdir)

    with _Session(_engine) as _s:
        _book = Book(
            title="MP3 Test", source_path=str(_tmpdir / "test.epub"),
            status=BookStatus.ANALYZED,
        )
        _s.add(_book)
        _s.commit()
        _s.refresh(_book)
        _bid = _book.id

        _ch = Chapter(book_id=_bid, position=1, title="Ch1", raw_text="x")
        _s.add(_ch)
        _s.commit()
        _s.refresh(_ch)

        _s.add(Segment(
            chapter_id=_ch.id, position=1, text="Une phrase.",
            segment_type=SegmentType.NARRATION, character_id=None,
        ))
        _s.commit()

    async def _mp3_fake_tts(text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        return _make_wav(n_frames=100)

    _mock_tts = MagicMock()
    _mock_tts.synthesise = AsyncMock(side_effect=_mp3_fake_tts)

    with (
        patch("app.core.db.get_engine", return_value=_engine),
        patch("app.services.tts.factory.get_tts_provider", return_value=_mock_tts),
    ):
        from app.workers.tasks import _generate_book_impl
        _generate_book_impl(_bid)

    with _Session(_engine) as _s:
        _b = _s.get(Book, _bid)
        check("status = DONE", _b.status == BookStatus.DONE, str(_b.status))
        check("mp3_path non nul", _b.mp3_path is not None)
        if _b.mp3_path:
            check("fichier MP3 sur disque", Path(_b.mp3_path).exists())
            check("mp3_path se termine par .mp3", _b.mp3_path.endswith(".mp3"))
        _ch_after = _s.exec(_select(Chapter).where(Chapter.book_id == _bid)).first()
        check("chapitre DONE (généré via le nouveau chemin unifié)",
              _ch_after.status == ChapterStatus.DONE, f"got {_ch_after.status}")


# ── 8. GET /books/{id}/audio/mp3 -- 200 OK ───────────────────────────────────
section("GET /books/{id}/audio/mp3 -- 200 OK avec fichier MP3")
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import get_session as _real_get_session  # noqa: E402


def _get_test_session():
    with _Session(_engine) as s:
        yield s


app.dependency_overrides[_real_get_session] = _get_test_session
client = TestClient(app)

with _tf.TemporaryDirectory() as _tmpdir2:
    _mp3_file = Path(_tmpdir2) / "book.mp3"
    _mp3_file.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)

    with _Session(_engine) as _s:
        _book2 = Book(title="MP3 Serve", source_path="x.epub", mp3_path=str(_mp3_file))
        _s.add(_book2)
        _s.commit()
        _s.refresh(_book2)
        _bid2 = _book2.id

    resp = client.get(f"/books/{_bid2}/audio/mp3")
    check("status 200", resp.status_code == 200, str(resp.status_code))
    check("content-type audio/mpeg", "audio/mpeg" in resp.headers.get("content-type", ""))


# ── 9. GET /books/{id}/audio/mp3 -- 404 si pas de mp3_path ───────────────────
section("GET /books/{id}/audio/mp3 -- 404 si book sans mp3_path")
with _Session(_engine) as _s:
    _book3 = Book(title="No MP3", source_path="y.epub")
    _s.add(_book3)
    _s.commit()
    _s.refresh(_book3)
    _bid3 = _book3.id

resp = client.get(f"/books/{_bid3}/audio/mp3")
check("status 404", resp.status_code == 404, str(resp.status_code))
check("detail mentionne MP3", "MP3" in resp.json().get("detail", ""))

app.dependency_overrides.clear()


# ── Resume ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
