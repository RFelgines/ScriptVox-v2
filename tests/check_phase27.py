"""check_phase27.py — Phase 27 (Lot C1, audit 2026-07-02) : unification de la
génération livre sur le chemin chapitre.

Valide :
  - Happy path : génération livre = itération sur les chapitres, book.wav assemblé
    depuis les WAV chapitres sur disque, chapitres DONE avec audio_path + timing.
  - Reprise après échec : un chapitre déjà DONE (résume-après-FAILED) n'est jamais
    resynthétisé.
  - Régénération complète (pas resume) : "Regénérer l'audio" sur un livre DONE
    refait bien TOUS les chapitres (pas de no-op silencieux).
  - Échec partiel : ch.1 DONE reste DONE, ch.2 FAILED -> livre FAILED.
  - /stop à granularité segment : abandon au milieu d'un chapitre -> rien persisté,
    chapitre revert à PENDING, TTS appelé une seule fois.
  - /stop entre chapitres : ch.1 déjà DONE n'est PAS perdu, ch.2 jamais entamé.
  - POST /books/{id}/generate accepte désormais FAILED (resume déclenchable).
  - Livre sans chapitres -> toujours DONE, audio_path=None (comportement préexistant).
  - assemble_wav_from_files : concaténation depuis le disque + garde-fou format.

Run: .venv/Scripts/python tests/check_phase27.py
"""
import io
import os
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p27.db",
    "HUEY_DB_PATH": "./huey_test_p27.db",
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
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.services.audio.assembler import assemble_wav_from_files  # noqa: E402
from app.workers.tasks import _generate_book_impl  # noqa: E402
ok("_generate_book_impl, assemble_wav_from_files, models, enums")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_book_with_chapters(engine, chapters_segments: list[list[str]], source_path: str, **book_kwargs):
    """chapters_segments = une liste par chapitre, de textes de segment."""
    with Session(engine) as s:
        book = Book(title="C1Test", source_path=source_path, **book_kwargs)
        s.add(book)
        s.commit()
        s.refresh(book)
        book_id = book.id
        chapter_ids = []
        for pos, texts in enumerate(chapters_segments, start=1):
            ch = Chapter(book_id=book_id, position=pos, title=f"Ch{pos}", raw_text="x")
            s.add(ch)
            s.commit()
            s.refresh(ch)
            chapter_ids.append(ch.id)
            for spos, text in enumerate(texts, start=1):
                s.add(Segment(
                    chapter_id=ch.id, position=spos, text=text,
                    segment_type=SegmentType.NARRATION, character_id=None,
                ))
            s.commit()
    return book_id, chapter_ids


def _simulate_user_stop(engine, book_id: int) -> None:
    with Session(engine) as s:
        b = s.get(Book, book_id)
        b.status = BookStatus.FAILED
        b.error_message = "Arrêté par l'utilisateur."
        s.add(b)
        s.commit()


class _CountingTTS:
    """Chaque appel synthesise() renvoie un WAV valide ; peut lever une TTSError
    pour un texte de segment donné, ou appeler un hook après un compteur d'appels."""

    def __init__(self, fail_on_text: str | None = None, hook_at_call: int | None = None, hook=None):
        self.calls = 0
        self.texts: list[str] = []
        self._fail_on_text = fail_on_text
        self._hook_at_call = hook_at_call
        self._hook = hook

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        self.calls += 1
        self.texts.append(text)
        if self._hook_at_call is not None and self.calls == self._hook_at_call and self._hook:
            self._hook()
        if self._fail_on_text is not None and text == self._fail_on_text:
            raise TTSError(f"mock:{voice_id}", RuntimeError("forced failure"))
        return _make_wav_bytes(50)


# ── 2. Happy path : 2 chapitres -> book.wav assemblé, chapitres DONE ─────────
section("Happy path : génération livre = 2 chapitres DONE, book.wav concaténé depuis le disque")
_e2 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp2:
    _src2 = str(Path(_tmp2) / "book.epub")
    _bid2, _chids2 = _make_book_with_chapters(
        _e2, [["Un.", "Deux."], ["Trois."]], _src2, status=BookStatus.ANALYZED,
    )
    _tts2 = _CountingTTS()
    with (
        patch("app.core.db.get_engine", return_value=_e2),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts2),
    ):
        _generate_book_impl(_bid2)

    with Session(_e2) as _s:
        _b2 = _s.get(Book, _bid2)
        check("livre DONE", _b2.status == BookStatus.DONE, f"got {_b2.status}")
        check("progress=100.0", _b2.progress == 100.0, f"got {_b2.progress}")
        check("audio_path renseigné", _b2.audio_path is not None)
        check("mp3_path renseigné", _b2.mp3_path is not None)
        if _b2.audio_path:
            check("book.wav existe sur disque", Path(_b2.audio_path).exists())
        if _b2.mp3_path:
            check("book.mp3 existe sur disque", Path(_b2.mp3_path).exists())

        _chapters2 = _s.exec(
            select(Chapter).where(Chapter.book_id == _bid2).order_by(Chapter.position)
        ).all()
        for _ch in _chapters2:
            check(f"chapitre {_ch.position} DONE", _ch.status == ChapterStatus.DONE,
                  f"got {_ch.status}")
            check(f"chapitre {_ch.position} a un audio_path sur disque",
                  bool(_ch.audio_path) and Path(_ch.audio_path).exists())

        _segs2 = _s.exec(
            select(Segment).where(Segment.chapter_id.in_(_chids2)).order_by(Segment.id)
        ).all()
        check("timing persisté pour tous les segments",
              all(s.audio_offset_ms is not None and s.duration_ms is not None for s in _segs2),
              f"got {[(s.audio_offset_ms, s.duration_ms) for s in _segs2]}")
    check("4 segments synthétisés (2+1... attendu 3)", _tts2.calls == 3, f"got {_tts2.calls}")


# ── 3. Reprise après échec : chapitre déjà DONE jamais resynthétisé ──────────
section("Reprise (resume après FAILED) : chapitre 1 déjà DONE -> jamais resynthétisé")
_e3 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp3:
    _src3 = str(Path(_tmp3) / "book.epub")
    _bid3, _chids3 = _make_book_with_chapters(
        _e3, [["Un."], ["Deux."]], _src3, status=BookStatus.ANALYZED,
    )
    # 1er run : tout génère normalement.
    _tts3a = _CountingTTS()
    with (
        patch("app.core.db.get_engine", return_value=_e3),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts3a),
    ):
        _generate_book_impl(_bid3)
    with Session(_e3) as _s:
        check("run 1 : livre DONE", _s.get(Book, _bid3).status == BookStatus.DONE)

    # Simule un échec après coup (comme si /stop ou une erreur avait eu lieu),
    # puis relance : le chapitre 1 (déjà DONE) ne doit pas être retouché.
    with Session(_e3) as _s:
        b = _s.get(Book, _bid3)
        b.status = BookStatus.FAILED
        b.error_message = "erreur simulée"
        _s.add(b)
        _s.commit()

    _tts3b = _CountingTTS()
    with (
        patch("app.core.db.get_engine", return_value=_e3),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts3b),
    ):
        _generate_book_impl(_bid3)

    check("run 2 (reprise) : TTS jamais rappelé (les 2 chapitres étaient déjà DONE)",
          _tts3b.calls == 0, f"got {_tts3b.calls}")
    with Session(_e3) as _s:
        check("livre à nouveau DONE après reprise", _s.get(Book, _bid3).status == BookStatus.DONE)


# ── 4. Régénération complète (pas resume) : TOUS les chapitres sont refaits ──
section("Régénération complète (status=DONE, pas FAILED) : tous les chapitres sont refaits")
_e4 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp4:
    _src4 = str(Path(_tmp4) / "book.epub")
    _bid4, _chids4 = _make_book_with_chapters(
        _e4, [["Un."], ["Deux."]], _src4, status=BookStatus.ANALYZED,
    )
    _tts4a = _CountingTTS()
    with (
        patch("app.core.db.get_engine", return_value=_e4),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts4a),
    ):
        _generate_book_impl(_bid4)  # book.status devient DONE

    _tts4b = _CountingTTS()
    with (
        patch("app.core.db.get_engine", return_value=_e4),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts4b),
    ):
        _generate_book_impl(_bid4)  # "Regénérer l'audio" sur un livre DONE

    check("les 2 segments sont resynthétisés (pas de no-op silencieux)",
          _tts4b.calls == 2, f"got {_tts4b.calls}")


# ── 5. Échec partiel : ch.1 DONE reste DONE, ch.2 FAILED -> livre FAILED ─────
section("Échec partiel : chapitre 1 reste DONE, chapitre 2 FAILED, livre FAILED")
_e5 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp5:
    _src5 = str(Path(_tmp5) / "book.epub")
    _bid5, _chids5 = _make_book_with_chapters(
        _e5, [["Un."], ["ECHEC_ICI"]], _src5, status=BookStatus.ANALYZED,
    )
    _tts5 = _CountingTTS(fail_on_text="ECHEC_ICI")
    with (
        patch("app.core.db.get_engine", return_value=_e5),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts5),
    ):
        _generate_book_impl(_bid5)

    with Session(_e5) as _s:
        _b5 = _s.get(Book, _bid5)
        check("livre FAILED", _b5.status == BookStatus.FAILED, f"got {_b5.status}")
        check("error_message renseigné", bool(_b5.error_message))

        _ch1, _ch2 = _s.exec(
            select(Chapter).where(Chapter.book_id == _bid5).order_by(Chapter.position)
        ).all()
        check("chapitre 1 reste DONE (pas perdu)", _ch1.status == ChapterStatus.DONE,
              f"got {_ch1.status}")
        check("chapitre 2 FAILED avec error_message", _ch2.status == ChapterStatus.FAILED
              and bool(_ch2.error_message), f"got {_ch2.status}, {_ch2.error_message!r}")


# ── 6. /stop à granularité segment : abandon au milieu d'un chapitre ─────────
section("/stop granularité segment : abandon mi-chapitre -> rien persisté, chapitre PENDING")
_e6 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp6:
    _src6 = str(Path(_tmp6) / "book.epub")
    _bid6, _chids6 = _make_book_with_chapters(
        _e6, [["Un.", "Deux.", "Trois.", "Quatre."]], _src6, status=BookStatus.ANALYZED,
    )
    _tts6 = _CountingTTS(hook_at_call=1, hook=lambda: _simulate_user_stop(_e6, _bid6))
    with (
        patch("app.core.db.get_engine", return_value=_e6),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts6),
    ):
        _generate_book_impl(_bid6)

    check("un seul segment synthétisé avant l'abandon (sur 4)", _tts6.calls == 1,
          f"got {_tts6.calls}")
    with Session(_e6) as _s:
        _b6 = _s.get(Book, _bid6)
        check("livre FAILED", _b6.status == BookStatus.FAILED, f"got {_b6.status}")
        check("audio_path jamais écrit", _b6.audio_path is None)
        _ch6 = _s.exec(select(Chapter).where(Chapter.book_id == _bid6)).first()
        check("chapitre reverti à PENDING (pas DONE, rien persisté)",
              _ch6.status == ChapterStatus.PENDING, f"got {_ch6.status}")
        check("chapitre sans audio_path", _ch6.audio_path is None)
        _segs6 = _s.exec(select(Segment).where(Segment.chapter_id == _ch6.id)).all()
        check("aucun timing persisté sur les segments du chapitre interrompu",
              all(s.audio_offset_ms is None for s in _segs6),
              f"got {[s.audio_offset_ms for s in _segs6]}")


# ── 7. /stop entre chapitres : ch.1 déjà DONE n'est pas perdu ────────────────
section("/stop entre chapitres : chapitre 1 (déjà DONE) préservé, chapitre 2 jamais entamé")
_e7 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp7:
    _src7 = str(Path(_tmp7) / "book.epub")
    _bid7, _chids7 = _make_book_with_chapters(
        _e7, [["Un."], ["Deux."]], _src7, status=BookStatus.ANALYZED,
    )
    # Le stop est simulé APRÈS la fin du 1er segment (= fin du chapitre 1, qui n'a
    # qu'un segment) -- le check "avant chapitre suivant" de _generate_book_async
    # doit alors empêcher le chapitre 2 de démarrer.
    _tts7 = _CountingTTS(hook_at_call=1, hook=lambda: _simulate_user_stop(_e7, _bid7))
    with (
        patch("app.core.db.get_engine", return_value=_e7),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts7),
    ):
        _generate_book_impl(_bid7)

    check("un seul appel TTS (chapitre 1, 1 segment)", _tts7.calls == 1, f"got {_tts7.calls}")
    with Session(_e7) as _s:
        _ch1_7, _ch2_7 = _s.exec(
            select(Chapter).where(Chapter.book_id == _bid7).order_by(Chapter.position)
        ).all()
        check("chapitre 1 va au bout et reste DONE (le stop est détecté APRÈS son "
              "seul segment, donc avant de démarrer le chapitre 2 seulement)",
              _ch1_7.status == ChapterStatus.DONE, f"got {_ch1_7.status}")
        check("chapitre 2 jamais entamé (toujours PENDING)",
              _ch2_7.status == ChapterStatus.PENDING, f"got {_ch2_7.status}")


# ── 8. POST /books/{id}/generate accepte désormais FAILED ────────────────────
section("POST /books/{id}/generate : accepte FAILED (reprise déclenchable via l'API)")
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

_e8 = _make_test_engine()
with Session(_e8) as _s:
    _b8 = Book(title="ResumeAPI", source_path="/tmp/x.epub", status=BookStatus.FAILED)
    _s.add(_b8)
    _s.commit()
    _s.refresh(_b8)
    _b8_id = _b8.id


def _session8():
    with Session(_e8) as s:
        yield s


app.dependency_overrides[get_session] = _session8
with patch("app.core.db.get_engine", return_value=_e8):
    with patch("app.workers.tasks.generate_book") as _mock_dispatch8:
        with TestClient(app, raise_server_exceptions=False) as _tc:
            _r8 = _tc.post(f"/books/{_b8_id}/generate")
            check("202 accepté (status FAILED)", _r8.status_code == 202,
                  f"got {_r8.status_code} ({_r8.text})")
app.dependency_overrides.clear()


# ── 9. Livre sans chapitre -> toujours DONE, audio_path=None ─────────────────
section("Régression : livre sans chapitre -> DONE, audio_path=None (comportement préexistant)")
_e9 = _make_test_engine()
with Session(_e9) as _s:
    _b9 = Book(title="Empty", source_path="/tmp/empty.epub", status=BookStatus.ANALYZED)
    _s.add(_b9)
    _s.commit()
    _s.refresh(_b9)
    _b9_id = _b9.id

with patch("app.core.db.get_engine", return_value=_e9):
    _generate_book_impl(_b9_id)

with Session(_e9) as _s:
    _b9_after = _s.get(Book, _b9_id)
    check("livre DONE malgré l'absence de chapitres", _b9_after.status == BookStatus.DONE,
          f"got {_b9_after.status}")
    check("audio_path=None", _b9_after.audio_path is None)
    check("mp3_path=None", _b9_after.mp3_path is None)


# ── 10. assemble_wav_from_files : concaténation + garde-fou format ───────────
section("assemble_wav_from_files : concatène depuis le disque, garde-fou de format inchangé")
with tempfile.TemporaryDirectory() as _tmp10:
    _p1 = Path(_tmp10) / "a.wav"
    _p2 = Path(_tmp10) / "b.wav"
    _p1.write_bytes(_make_wav_bytes(100))
    _p2.write_bytes(_make_wav_bytes(50))
    _out = Path(_tmp10) / "out.wav"
    assemble_wav_from_files([_p1, _p2], _out)
    with wave.open(str(_out), "rb") as _wf:
        check("150 frames au total (100+50)", _wf.getnframes() == 150, f"got {_wf.getnframes()}")
        check("22050 Hz mono 16-bit", (_wf.getnchannels(), _wf.getsampwidth(), _wf.getframerate()) == (1, 2, 22050))

    _p3_mismatch = Path(_tmp10) / "c.wav"
    _p3_mismatch.write_bytes(_make_wav_bytes(50, framerate=16000))
    try:
        assemble_wav_from_files([_p1, _p3_mismatch], Path(_tmp10) / "out2.wav")
        fail("Expected ValueError sur un mismatch de format")
    except ValueError as exc:
        ok(f"ValueError levée sur mismatch de format : {exc}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p27.db", "huey_test_p27.db"):
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
