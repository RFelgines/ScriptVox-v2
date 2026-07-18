"""check_phase40.py — Phase 40 (audit 2026-07-11, T2.3) : Book.failed_stage.

Contexte : un livre FAILED ne disait pas jusqu'ici si c'est l'ANALYSE ou la
GÉNÉRATION qui a échoué -- l'UI proposait donc parfois le mauvais bouton de
reprise (ex. "Reprendre l'analyse" sur un livre dont seule la génération a
échoué, ce qui repasse le livre en ANALYZED et casse la possibilité de
reprendre la génération interrompue, cf. finding pipeline audit 2026-07-11).
Nouvelle colonne Book.failed_stage ("analysis" | "generation" | None),
migration 67521bdee0e5.

Valide :
  - _analyze_book_impl échoue (exception LLM) -> failed_stage="analysis".
  - _generate_book_impl échoue (exception TTS) -> failed_stage="generation".
  - POST /books/{id}/stop pendant PROCESSING -> failed_stage="analysis".
  - POST /books/{id}/stop pendant GENERATING -> failed_stage="generation".
  - _reconcile_zombie_state (@huey.on_startup) : PROCESSING zombie ->
    "analysis" ; GENERATING zombie -> "generation".
  - Stop d'UN chapitre pendant une génération pilotée par le livre
    (_generate_book_async, combined stop checker T1.5) -> "generation".
  - Une analyse qui réussit après un échec précédent -> failed_stage remis à
    None (jamais de valeur périmée sur un livre reparti à zéro).
  - GET /books/{id} expose failed_stage (BookResponse).

Run: .venv/Scripts/python tests/check_phase40.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p40.db",
    "HUEY_DB_PATH": "./huey_test_p40.db",
    "DATA_DIR": "./data_test",
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


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
import asyncio  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.schemas.book import BookResponse  # noqa: E402
from app.workers.tasks import (  # noqa: E402
    _analyze_book_impl,
    _generate_book_impl,
    _generate_book_async,
    _reconcile_zombie_state,
)
ok("_analyze_book_impl, _generate_book_impl, _generate_book_async, _reconcile_zombie_state, BookResponse")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


check("BookResponse expose failed_stage", "failed_stage" in BookResponse.model_fields)


# ── 2. _analyze_book_impl échoue -> failed_stage="analysis" ─────────────────
section("_analyze_book_impl : exception LLM -> failed_stage='analysis'")
_e2 = _make_test_engine()
with Session(_e2) as _s:
    _b2 = Book(title="AnalysisFails", source_path="/tmp/does-not-exist.epub")
    _s.add(_b2)
    _s.commit()
    _b2_id = _b2.id

with patch("app.core.db.get_engine", return_value=_e2):
    # EpubParser.parse() lève sur un fichier inexistant -- déclenche le except
    # de _analyze_book_impl avant même le 1er appel LLM.
    _analyze_book_impl(_b2_id)

with Session(_e2) as _s:
    _b2_after = _s.get(Book, _b2_id)
    check("status FAILED", _b2_after.status == BookStatus.FAILED, f"got {_b2_after.status}")
    check("failed_stage='analysis'", _b2_after.failed_stage == "analysis",
          f"got {_b2_after.failed_stage!r}")


# ── 3. _generate_book_impl échoue -> failed_stage="generation" ──────────────
section("_generate_book_impl : exception TTS -> failed_stage='generation'")
_e3 = _make_test_engine()
with Session(_e3) as _s:
    _b3 = Book(title="GenerationFails", source_path="/tmp/x.epub", status=BookStatus.ANALYZED)
    _s.add(_b3)
    _s.commit()
    _b3_id = _b3.id
    _ch3 = Chapter(book_id=_b3_id, position=1, title="Ch1", raw_text="x")
    _s.add(_ch3)
    _s.commit()
    _s.refresh(_ch3)
    _s.add(Segment(chapter_id=_ch3.id, position=1, text="x", segment_type=SegmentType.NARRATION))
    _s.commit()


class _FailingTTS3:
    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        raise RuntimeError("TTS en panne simulée")


with (
    patch("app.core.db.get_engine", return_value=_e3),
    patch("app.services.tts.factory.get_tts_provider", return_value=_FailingTTS3()),
):
    _generate_book_impl(_b3_id)

with Session(_e3) as _s:
    _b3_after = _s.get(Book, _b3_id)
    check("status FAILED", _b3_after.status == BookStatus.FAILED, f"got {_b3_after.status}")
    check("failed_stage='generation'", _b3_after.failed_stage == "generation",
          f"got {_b3_after.failed_stage!r}")


# ── 4. POST /stop pendant PROCESSING -> failed_stage="analysis" ─────────────
section("POST /books/{id}/stop pendant PROCESSING -> failed_stage='analysis'")
from fastapi.testclient import TestClient  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

_e4 = _make_test_engine()
with Session(_e4) as _s:
    _b4 = Book(title="StopDuringAnalysis", source_path="/tmp/x.epub", status=BookStatus.PROCESSING)
    _s.add(_b4)
    _s.commit()
    _b4_id = _b4.id


def _session4():
    with Session(_e4) as s:
        yield s


app.dependency_overrides[get_session] = _session4
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r4 = _tc.post(f"/books/{_b4_id}/stop")
app.dependency_overrides.pop(get_session, None)

check("200", _r4.status_code == 200, f"got {_r4.status_code}: {_r4.text}")
check("réponse failed_stage='analysis'", _r4.json().get("failed_stage") == "analysis",
      f"got {_r4.json()}")
with Session(_e4) as _s:
    _b4_after = _s.get(Book, _b4_id)
    check("DB failed_stage='analysis'", _b4_after.failed_stage == "analysis",
          f"got {_b4_after.failed_stage!r}")


# ── 5. POST /stop pendant GENERATING -> failed_stage="generation" ───────────
section("POST /books/{id}/stop pendant GENERATING -> failed_stage='generation'")
_e5 = _make_test_engine()
with Session(_e5) as _s:
    _b5 = Book(title="StopDuringGeneration", source_path="/tmp/x.epub", status=BookStatus.GENERATING)
    _s.add(_b5)
    _s.commit()
    _b5_id = _b5.id


def _session5():
    with Session(_e5) as s:
        yield s


app.dependency_overrides[get_session] = _session5
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r5 = _tc.post(f"/books/{_b5_id}/stop")
app.dependency_overrides.pop(get_session, None)

check("200", _r5.status_code == 200, f"got {_r5.status_code}: {_r5.text}")
check("réponse failed_stage='generation'", _r5.json().get("failed_stage") == "generation",
      f"got {_r5.json()}")


# ── 6. _reconcile_zombie_state : PROCESSING/GENERATING -> stage correct ─────
section("_reconcile_zombie_state : PROCESSING->'analysis', GENERATING->'generation'")
_e6 = _make_test_engine()
with Session(_e6) as _s:
    _b6a = Book(title="ZombieAnalysis", source_path="/tmp/a.epub", status=BookStatus.PROCESSING)
    _b6b = Book(title="ZombieGeneration", source_path="/tmp/b.epub", status=BookStatus.GENERATING)
    _s.add(_b6a)
    _s.add(_b6b)
    _s.commit()
    _b6a_id, _b6b_id = _b6a.id, _b6b.id

with patch("app.core.db.get_engine", return_value=_e6):
    _reconcile_zombie_state()

with Session(_e6) as _s:
    _b6a_after = _s.get(Book, _b6a_id)
    _b6b_after = _s.get(Book, _b6b_id)
    check("zombie PROCESSING -> failed_stage='analysis'",
          _b6a_after.failed_stage == "analysis", f"got {_b6a_after.failed_stage!r}")
    check("zombie GENERATING -> failed_stage='generation'",
          _b6b_after.failed_stage == "generation", f"got {_b6b_after.failed_stage!r}")


# ── 7. Stop d'UN chapitre pendant génération livre -> "generation" ──────────
# Combined stop checker (T1.5, audit 2026-07-11) : Chapter.cancel_requested du
# chapitre en cours de synthèse fait basculer le LIVRE en FAILED lui-même
# (Book.status était encore GENERATING) -- ce chemin doit aussi renseigner
# failed_stage="generation", pas seulement le chemin except() générique.
section("_generate_book_async : stop d'un chapitre en cours -> Book.failed_stage='generation'")
_e7 = _make_test_engine()
with Session(_e7) as _s:
    _b7 = Book(title="ChapterStopMidBook", source_path="/tmp/y.epub", status=BookStatus.GENERATING)
    _s.add(_b7)
    _s.commit()
    _b7_id = _b7.id
    _ch7 = Chapter(book_id=_b7_id, position=1, title="Ch1", raw_text="x")
    _s.add(_ch7)
    _s.commit()
    _s.refresh(_ch7)
    _s.add(Segment(chapter_id=_ch7.id, position=1, text="Segment1", segment_type=SegmentType.NARRATION))
    _s.add(Segment(chapter_id=_ch7.id, position=2, text="Segment2", segment_type=SegmentType.NARRATION))
    _s.commit()
    _ch7_id = _ch7.id


class _CancelAfterFirstTTS7:
    def __init__(self, engine, chapter_id):
        self._engine = engine
        self._chapter_id = chapter_id
        self.calls = 0

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        self.calls += 1
        if self.calls == 1:
            with Session(self._engine) as s:
                c = s.get(Chapter, self._chapter_id)
                c.cancel_requested = True
                s.add(c)
                s.commit()
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 50)
        return buf.getvalue()


_tts7 = _CancelAfterFirstTTS7(_e7, _ch7_id)
with (
    patch("app.core.db.get_engine", return_value=_e7),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts7),
):
    _completed7 = asyncio.run(_generate_book_async(_b7_id, _e7))

check("_generate_book_async retourne False (abandon)", _completed7 is False, f"got {_completed7}")
with Session(_e7) as _s:
    _b7_after = _s.get(Book, _b7_id)
    check("Book.status = FAILED", _b7_after.status == BookStatus.FAILED, f"got {_b7_after.status}")
    check("Book.failed_stage = 'generation'", _b7_after.failed_stage == "generation",
          f"got {_b7_after.failed_stage!r}")


# ── 8. Succès après échec précédent -> failed_stage remis à None ────────────
section("Analyse réussie après un échec précédent -> failed_stage remis à None")
_e8 = _make_test_engine()
with Session(_e8) as _s:
    _b8 = Book(
        title="RetryAfterFail", source_path=str(ROOT / "tests" / "fixtures" / "test.epub"),
        status=BookStatus.FAILED, failed_stage="analysis", error_message="Une vraie erreur.",
    )
    _s.add(_b8)
    _s.commit()
    _b8_id = _b8.id

_fixture_epub = ROOT / "tests" / "fixtures" / "test.epub"
if not _fixture_epub.exists():
    fail("fixture epub manquante", str(_fixture_epub))
else:
    from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData
    from app.core.enums import Gender

    class _SucceedingLLM8:
        async def analyze(self, text, known_characters=None, language=None):
            return LLMChapterResult(
                characters=[CharacterData(name="Alice", description=None, gender=Gender.FEMALE)],
                segments=[SegmentData(
                    position=1, text=text or "x",
                    segment_type=SegmentType.NARRATION, character_name=None,
                )],
            )

        async def suggest_merges(self, characters):
            return []

    with (
        patch("app.core.db.get_engine", return_value=_e8),
        patch("app.services.llm.factory.get_llm_provider", return_value=_SucceedingLLM8()),
    ):
        _analyze_book_impl(_b8_id, force=True)

    with Session(_e8) as _s:
        _b8_after = _s.get(Book, _b8_id)
        check("status ANALYZED", _b8_after.status == BookStatus.ANALYZED, f"got {_b8_after.status}")
        check("failed_stage remis à None (pas de valeur périmée)",
              _b8_after.failed_stage is None, f"got {_b8_after.failed_stage!r}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p40.db", "huey_test_p40.db"):
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
