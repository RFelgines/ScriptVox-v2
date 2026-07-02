"""check_phase24.py — Phase 24 (Lots F1b + B1a, audit 2026-07-02).

Valide :
  - F1b : la VRAM chargée par Qwen3-TTS est libérée après une génération normale
          (livre ou chapitre), pas seulement après l'aperçu de voix clonée.
  - B1a : un livre peut surcharger vers "piper" sans faire planter le worker en
          AttributeError si Piper n'est pas le provider global configuré --
          Settings peuple toujours piper_voices_dir/piper_binary_path (None si
          absents), et PiperProvider lève une TTSError explicite plutôt qu'une
          AttributeError quand ils manquent.

Run: .venv/Scripts/python tests/check_phase24.py
"""
import asyncio
import io
import os
import sys
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p24.db",
    "HUEY_DB_PATH": "./huey_test_p24.db",
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


def _make_wav_bytes(n_frames: int, framerate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.core.enums import BookStatus, SegmentType  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.services.tts.factory import get_tts_provider  # noqa: E402
from app.services.tts.piper import PiperProvider  # noqa: E402
from app.services.tts.qwen import QwenTTSProvider  # noqa: E402
from app.workers.tasks import (  # noqa: E402
    _release_qwen_gpu,
    _synthesise_book,
    _synthesise_chapter_worker,
)
ok("PiperProvider, QwenTTSProvider, get_tts_provider, tasks helpers")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _simulate_user_stop(engine, book_id: int) -> None:
    with Session(engine) as s:
        b = s.get(Book, book_id)
        b.status = BookStatus.FAILED
        b.error_message = "Arrêté par l'utilisateur."
        s.add(b)
        s.commit()


# ═══════════════════════════════ F1b ═══════════════════════════════════════

# ── 2. _release_qwen_gpu no-op sur un provider non-Qwen ───────────────────────
section("F1b: _release_qwen_gpu() ne fait rien pour un provider non-Qwen")
_mock_provider2 = MagicMock()
_mock_provider2.some_attr = "untouched"
try:
    _release_qwen_gpu(_mock_provider2)
    ok("aucune exception levée")
    check("provider non-Qwen inchangé", _mock_provider2.some_attr == "untouched")
except Exception as exc:
    fail("_release_qwen_gpu ne devrait jamais lever", f"{type(exc).__name__}: {exc}")


# ── 3. _release_qwen_gpu libère _model/_base_model sur un vrai QwenTTSProvider
section("F1b: _release_qwen_gpu() remet _model/_base_model à None sur QwenTTSProvider")
_qwen3 = QwenTTSProvider(SimpleNamespace())
_qwen3._model = object()       # simule un checkpoint CustomVoice chargé
_qwen3._base_model = object()  # simule un checkpoint Base chargé
try:
    _release_qwen_gpu(_qwen3)
    check("_model remis à None", _qwen3._model is None)
    check("_base_model remis à None", _qwen3._base_model is None)
except Exception as exc:
    fail("_release_qwen_gpu ne devrait pas lever (torch installé dans ce venv)",
         f"{type(exc).__name__}: {exc}")


# ── 4. _synthesise_book libère la VRAM après une génération réussie ──────────
section("F1b: _synthesise_book() libère provider._model après une génération réussie")
_e4 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp4:
    _src4 = str(Path(_tmp4) / "book.epub")
    with Session(_e4) as _s:
        _b4 = Book(title="QwenRelease", source_path=_src4, status=BookStatus.ANALYZED)
        _s.add(_b4)
        _s.commit()
        _s.refresh(_b4)
        _b4_id = _b4.id
        _ch4 = Chapter(book_id=_b4_id, position=1, title="Ch1", raw_text="peu importe")
        _s.add(_ch4)
        _s.commit()
        _s.refresh(_ch4)
        _s.add(Segment(
            chapter_id=_ch4.id, position=1, text="Un.",
            segment_type=SegmentType.NARRATION, character_id=None,
        ))
        _s.commit()

    _provider4 = QwenTTSProvider(SimpleNamespace())
    _provider4._model = object()
    _provider4.synthesise = AsyncMock(return_value=_make_wav_bytes(50))

    with (
        patch("app.core.db.get_engine", return_value=_e4),
        patch("app.services.tts.factory.get_tts_provider", return_value=_provider4),
    ):
        _result4 = asyncio.run(_synthesise_book(_b4_id, _src4, _e4))

    check("génération réussie (chemin WAV renvoyé)", bool(_result4), f"got {_result4!r}")
    check("provider._model libéré (None) après succès", _provider4._model is None,
          f"got {_provider4._model!r}")


# ── 5. _synthesise_book libère la VRAM même après un abandon (/stop, Lot A) ──
section("F1b: _synthesise_book() libère provider._model même après un /stop mi-course")
_e5 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp5:
    _src5 = str(Path(_tmp5) / "book.epub")
    with Session(_e5) as _s:
        _b5 = Book(title="QwenReleaseAbort", source_path=_src5, status=BookStatus.ANALYZED)
        _s.add(_b5)
        _s.commit()
        _s.refresh(_b5)
        _b5_id = _b5.id
        _ch5 = Chapter(book_id=_b5_id, position=1, title="Ch1", raw_text="peu importe")
        _s.add(_ch5)
        _s.commit()
        _s.refresh(_ch5)
        for _pos in (1, 2):
            _s.add(Segment(
                chapter_id=_ch5.id, position=_pos, text=f"Segment {_pos}.",
                segment_type=SegmentType.NARRATION, character_id=None,
            ))
        _s.commit()

    _provider5 = QwenTTSProvider(SimpleNamespace())
    _provider5._model = object()
    _calls5 = {"n": 0}

    async def _fake_synth5(text, voice_id, emotion=None, reference_audio_path=None):
        _calls5["n"] += 1
        if _calls5["n"] == 1:
            _simulate_user_stop(_e5, _b5_id)
        return _make_wav_bytes(50)

    _provider5.synthesise = _fake_synth5

    with (
        patch("app.core.db.get_engine", return_value=_e5),
        patch("app.services.tts.factory.get_tts_provider", return_value=_provider5),
    ):
        _result5 = asyncio.run(_synthesise_book(_b5_id, _src5, _e5))

    check("génération abandonnée (None renvoyé, cf. Lot A)", _result5 is None, f"got {_result5!r}")
    check("un seul segment synthétisé avant l'abandon", _calls5["n"] == 1, f"got {_calls5['n']}")
    check("provider._model libéré (None) même après un abandon", _provider5._model is None,
          f"got {_provider5._model!r}")


# ── 6. _synthesise_chapter_worker libère la VRAM après génération d'un chapitre
section("F1b: _synthesise_chapter_worker() libère provider._model après un chapitre")
_e6 = _make_test_engine()
with Session(_e6) as _s:
    _b6 = Book(title="ChapterRelease", source_path="x.epub")
    _s.add(_b6)
    _s.commit()
    _s.refresh(_b6)
    _ch6 = Chapter(book_id=_b6.id, position=1, title="Ch1", raw_text="peu importe")
    _s.add(_ch6)
    _s.commit()
    _s.refresh(_ch6)
    _s.add(Segment(
        chapter_id=_ch6.id, position=1, text="Un.",
        segment_type=SegmentType.NARRATION, character_id=None,
    ))
    _s.commit()
    _ch6_id = _ch6.id

_provider6 = QwenTTSProvider(SimpleNamespace())
_provider6._model = object()
_provider6.synthesise = AsyncMock(return_value=_make_wav_bytes(50))

with (
    patch("app.core.db.get_engine", return_value=_e6),
    patch("app.services.tts.factory.get_tts_provider", return_value=_provider6),
):
    _wav6, _timing6 = asyncio.run(_synthesise_chapter_worker(_ch6_id, _e6))

check("chapitre synthétisé (WAV non vide)", len(_wav6) > 0, f"got {len(_wav6)} bytes")
check("provider._model libéré (None) après génération d'un chapitre", _provider6._model is None,
      f"got {_provider6._model!r}")


# ═══════════════════════════════ B1a ═══════════════════════════════════════

# ── 7. Settings(TTS_PROVIDER=edgetts) n'exige plus les vars Piper ────────────
section("B1a: Settings(TTS_PROVIDER=edgetts) n'exige plus PIPER_VOICES_DIR/PIPER_BINARY_PATH")
os.environ["TTS_PROVIDER"] = "edgetts"
os.environ.pop("PIPER_VOICES_DIR", None)
os.environ.pop("PIPER_BINARY_PATH", None)
get_settings.cache_clear()
with patch("app.config.load_dotenv", lambda *a, **kw: None):
    try:
        _settings7 = get_settings()
        ok("Settings() construit sans lever (edgetts global, piper non configuré)")
        check("piper_voices_dir existe comme attribut, valeur None",
              _settings7.piper_voices_dir is None, f"got {_settings7.piper_voices_dir!r}")
        check("piper_binary_path existe comme attribut, valeur None",
              _settings7.piper_binary_path is None, f"got {_settings7.piper_binary_path!r}")
    except Exception as exc:
        fail("Settings() ne devrait pas lever", f"{type(exc).__name__}: {exc}")
get_settings.cache_clear()


# ── 8. Régression : Settings(TTS_PROVIDER=piper) fail-fast inchangé ──────────
section("B1a (régression): Settings(TTS_PROVIDER=piper) fail-fast inchangé si var absente")
os.environ["TTS_PROVIDER"] = "piper"
os.environ.pop("PIPER_VOICES_DIR", None)
os.environ.pop("PIPER_BINARY_PATH", None)
get_settings.cache_clear()
with patch("app.config.load_dotenv", lambda *a, **kw: None):
    try:
        get_settings()
        fail("Expected ValueError quand piper est le provider global et PIPER_VOICES_DIR absent")
    except ValueError as exc:
        check("ValueError mentionne PIPER_VOICES_DIR", "PIPER_VOICES_DIR" in str(exc), str(exc))
get_settings.cache_clear()
os.environ["TTS_PROVIDER"] = "edgetts"


# ── 9. PiperProvider lève TTSError (pas AttributeError) si non configuré ─────
section("B1a: PiperProvider(settings) lève TTSError explicite si piper_voices_dir/binary_path=None")
_fake_settings9 = SimpleNamespace(piper_voices_dir=None, piper_binary_path=None)
try:
    PiperProvider(_fake_settings9)
    fail("Expected TTSError quand piper_voices_dir/piper_binary_path sont None")
except TTSError as exc:
    ok(f"TTSError levée : {exc}")
except AttributeError as exc:
    fail("AttributeError levée au lieu de TTSError (bug M1 de l'audit)", str(exc))


# ── 10. PiperProvider lève TTSError si les chemins configurés n'existent pas ─
section("B1a: PiperProvider(settings) lève TTSError explicite si les chemins n'existent pas")
_fake_settings10 = SimpleNamespace(
    piper_voices_dir="./chemin_qui_n_existe_pas_xyz",
    piper_binary_path="./binaire_qui_n_existe_pas_xyz.exe",
)
try:
    PiperProvider(_fake_settings10)
    fail("Expected TTSError quand les chemins piper n'existent pas")
except TTSError as exc:
    ok(f"TTSError levée : {exc}")


# ── 11. Intégration factory : override piper non configuré -> TTSError propre
section("B1a intégration: get_tts_provider(override='piper') échoue proprement (pas d'AttributeError)")
os.environ["TTS_PROVIDER"] = "edgetts"
os.environ.pop("PIPER_VOICES_DIR", None)
os.environ.pop("PIPER_BINARY_PATH", None)
get_settings.cache_clear()
with patch("app.config.load_dotenv", lambda *a, **kw: None):
    _settings11 = get_settings()
try:
    get_tts_provider(_settings11, override="piper")
    fail("Expected TTSError quand piper est overridé sans être configuré")
except TTSError as exc:
    ok(f"TTSError proprement levée : {exc}")
except AttributeError as exc:
    fail("AttributeError levée au lieu de TTSError -- exactement le bug M1 de l'audit", str(exc))
get_settings.cache_clear()


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p24.db", "huey_test_p24.db"):
    try:
        if os.path.exists(_leftover):
            os.remove(_leftover)
    except PermissionError:
        pass  # Windows file lock — ignoré


# ── Résumé ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*52}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
