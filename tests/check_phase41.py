"""check_phase41.py — Phase 41 (audit 2026-07-11, Lot 3) : file de génération réelle.

Contexte : Chapter.priority existait déjà (colonne DB) mais n'était JAMAIS lu
par le worker -- seule la vue GET /chapters/queue le lisait pour l'AFFICHAGE.
Les deux routes de dispatch (unitaire et "tout") enfilaient une tâche Huey
generate_chapter PAR CHAPITRE, exécutées ensuite en FIFO d'enfilage par Huey,
jamais selon priority. Le drag & drop de la page Génération réordonnait donc
un affichage sans aucun effet sur l'exécution réelle.

Nouvelle colonne Chapter.queued_at (migration db9016b64888) : posée au
dispatch réel, effacée dès que le chapitre est pris en charge (GENERATING)
ou retiré/abandonné -- None = jamais demandé, distinct de status=PENDING
seul. Une seule tâche Huey "pompe" (generate_chapter_queue_pump) traite la
file un chapitre à la fois, en RELISANT priority à chaque tour de boucle
(pas une capture figée au moment de l'enfilage) -- un PATCH .../priority
pendant que la pompe tourne change réellement le prochain choisi.

Valide :
  - generate_chapter_queue_pump traite les chapitres en file par
    priority DESC puis position ASC.
  - La priorité est relue à CHAQUE tour : une repriorisation pendant le
    traitement du 1er chapitre change bien le 2e choisi.
  - _generate_chapter_impl efface queued_at dès qu'il prend la main
    (GENERATING) -- le chapitre sort de la file immédiatement, pas
    seulement une fois DONE.
  - Un chapitre abandonné (cancel_requested) qui revient à PENDING a
    queued_at=None -- jamais repris en boucle par la pompe.
  - POST .../chapters/{n}/generate (unitaire) pose queued_at + dispatche
    la pompe une fois.
  - POST .../chapters/generate ("tout") pose queued_at sur tous les
    chapitres éligibles + dispatche la pompe UNE SEULE fois (pas N).
  - GET /chapters/queue ne montre que GENERATING + (PENDING avec
    queued_at renseigné) -- un chapitre jamais demandé n'apparaît plus.

Run: .venv/Scripts/python tests/check_phase41.py
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p41.db",
    "HUEY_DB_PATH": "./huey_test_p41.db",
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
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
from datetime import datetime, timezone  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.workers.tasks import (  # noqa: E402
    _generate_chapter_impl,
    _generate_chapter_queue_pump_impl,
    generate_chapter_queue_pump,
)
ok("_generate_chapter_impl, _generate_chapter_queue_pump_impl, generate_chapter_queue_pump")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_book_with_chapters(engine, chapters_segments: list[list[str]], queue_all: bool = True):
    """Crée un Book ANALYZED avec N chapitres PENDING (segments donnés),
    tous en file (queued_at posé) si queue_all. Retourne (book_id, [chapter_id, ...])."""
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        book = Book(title="P41Test", source_path="/tmp/p41.epub", status=BookStatus.ANALYZED)
        s.add(book)
        s.commit()
        s.refresh(book)
        chapter_ids = []
        for i, texts in enumerate(chapters_segments, start=1):
            ch = Chapter(
                book_id=book.id, position=i, title=f"Ch{i}", raw_text="x",
                queued_at=now if queue_all else None,
            )
            s.add(ch)
            s.commit()
            s.refresh(ch)
            for pos, text in enumerate(texts, start=1):
                s.add(Segment(
                    chapter_id=ch.id, position=pos, text=text,
                    segment_type=SegmentType.NARRATION, character_id=None,
                ))
            s.commit()
            chapter_ids.append(ch.id)
        book_id = book.id
    return book_id, chapter_ids


class _RecordingTTS:
    """Synthesise toujours avec succès ; enregistre l'ordre des chapitres
    traités (via le texte du 1er segment de chaque chapitre) et permet un hook
    exécuté après chaque appel réussi (pour repriorer pendant l'exécution)."""

    def __init__(self, on_call=None):
        self.texts_seen: list[str] = []
        self._on_call = on_call

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        self.texts_seen.append(text)
        if self._on_call:
            self._on_call(text)
        return _make_wav_bytes(50)


# ── 2. Ordre de traitement : priority DESC puis position ASC ────────────────
section("generate_chapter_queue_pump : traite la file par priority DESC puis position ASC")
_e2 = _make_test_engine()
_bid2, _chs2 = _make_book_with_chapters(_e2, [["UnA"], ["UnB"], ["UnC"]])
with Session(_e2) as _s:
    # Chapitre 3 (position 3) mis en priorité haute -- doit passer AVANT 1 et 2.
    _c3 = _s.get(Chapter, _chs2[2])
    _c3.priority = 10
    _s.add(_c3)
    _s.commit()

_tts2 = _RecordingTTS()
with (
    patch("app.core.db.get_engine", return_value=_e2),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts2),
):
    # generate_chapter_queue_pump est une tâche Huey (@huey.task()) : un appel nu
    # ne fait qu'enfiler (voir huey.api.TaskWrapper.__call__ -> huey.enqueue),
    # jamais d'exécution synchrone sans consumer actif. _generate_chapter_queue_pump_impl
    # est la logique réelle, testable en direct -- même convention que
    # _generate_chapter_impl / generate_chapter.
    _generate_chapter_queue_pump_impl()

check("ordre = UnC (priority=10), UnA (position 1), UnB (position 2)",
      _tts2.texts_seen == ["UnC", "UnA", "UnB"], f"got {_tts2.texts_seen}")
with Session(_e2) as _s:
    for cid in _chs2:
        c = _s.get(Chapter, cid)
        check(f"chapitre {c.position} DONE", c.status == ChapterStatus.DONE, f"got {c.status}")


# ── 3. La priorité est RELUE à chaque tour (pas figée au démarrage) ─────────
section("La pompe relit priority à CHAQUE tour : repriorisation pendant l'exécution change le prochain choisi")
_e3 = _make_test_engine()
_bid3, _chs3 = _make_book_with_chapters(_e3, [["Un"], ["Deux"], ["Trois"]])
# Ordre initial (priority=0 partout) : Un, Deux, Trois (par position).
# Pendant le traitement de "Un", on repriorise Trois au-dessus de Deux.


def _reprioritize_after_first(text: str) -> None:
    if text == "Un":
        with Session(_e3) as s:
            c_trois = s.get(Chapter, _chs3[2])
            c_trois.priority = 5
            s.add(c_trois)
            s.commit()


_tts3 = _RecordingTTS(on_call=_reprioritize_after_first)
with (
    patch("app.core.db.get_engine", return_value=_e3),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts3),
):
    _generate_chapter_queue_pump_impl()

check("ordre = Un, Trois (repriorisé en cours de route), Deux",
      _tts3.texts_seen == ["Un", "Trois", "Deux"], f"got {_tts3.texts_seen}")


# ── 4. queued_at effacé dès la prise en charge (GENERATING), pas juste DONE ──
section("_generate_chapter_impl efface queued_at dès GENERATING (sort de la file immédiatement)")
_e4 = _make_test_engine()
_bid4, _chs4 = _make_book_with_chapters(_e4, [["Segment1"]])
_ch4_id = _chs4[0]


def _check_queued_at_cleared_during_generation(text: str) -> None:
    # Appelé PENDANT la synthèse -- à ce stade chapter.status doit déjà être
    # GENERATING et queued_at déjà effacé (posé avant l'appel TTS).
    with Session(_e4) as s:
        c = s.get(Chapter, _ch4_id)
        check("queued_at déjà None pendant la synthèse (pas seulement après)",
              c.queued_at is None, f"got {c.queued_at!r}")
        check("status déjà GENERATING pendant la synthèse",
              c.status == ChapterStatus.GENERATING, f"got {c.status}")


_tts4 = _RecordingTTS(on_call=_check_queued_at_cleared_during_generation)
with (
    patch("app.core.db.get_engine", return_value=_e4),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts4),
):
    _generate_chapter_impl(_ch4_id)

with Session(_e4) as _s:
    _c4_after = _s.get(Chapter, _ch4_id)
    check("chapitre DONE", _c4_after.status == ChapterStatus.DONE, f"got {_c4_after.status}")
    check("queued_at toujours None après succès", _c4_after.queued_at is None)


# ── 5. Chapitre abandonné (cancel_requested) -> queued_at=None au retour PENDING
section("Chapitre stoppé en cours -> revient à PENDING avec queued_at=None (pas repris en boucle)")
_e5 = _make_test_engine()
_bid5, _chs5 = _make_book_with_chapters(_e5, [["SegA", "SegB"]])
_ch5_id = _chs5[0]


def _cancel_after_first_call(text: str) -> None:
    if text == "SegA":
        with Session(_e5) as s:
            c = s.get(Chapter, _ch5_id)
            c.cancel_requested = True
            s.add(c)
            s.commit()


_tts5 = _RecordingTTS(on_call=_cancel_after_first_call)
with (
    patch("app.core.db.get_engine", return_value=_e5),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts5),
):
    _generate_chapter_impl(_ch5_id)

with Session(_e5) as _s:
    _c5_after = _s.get(Chapter, _ch5_id)
    check("chapitre revenu à PENDING (interrompu)",
          _c5_after.status == ChapterStatus.PENDING, f"got {_c5_after.status}")
    check("queued_at=None (pas repris automatiquement par la pompe)",
          _c5_after.queued_at is None, f"got {_c5_after.queued_at!r}")


# ── 6. POST .../chapters/{n}/generate (unitaire) : pose queued_at + dispatch pompe
section("POST /books/{id}/chapters/{n}/generate -- pose queued_at, dispatche la pompe une fois")
from fastapi.testclient import TestClient  # noqa: E402
import app.api.routes.books as books_module  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

_e6 = _make_test_engine()
_bid6, _chs6 = _make_book_with_chapters(_e6, [["x"]], queue_all=False)


def _session6():
    with Session(_e6) as s:
        yield s


app.dependency_overrides[get_session] = _session6
_pump_calls6 = []
books_module.generate_chapter_queue_pump = lambda: _pump_calls6.append(1)
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r6 = _tc.post(f"/books/{_bid6}/chapters/1/generate")
books_module.generate_chapter_queue_pump = generate_chapter_queue_pump  # restore
app.dependency_overrides.pop(get_session, None)

check("202", _r6.status_code == 202, f"got {_r6.status_code}: {_r6.text}")
check("pompe dispatchée une fois", len(_pump_calls6) == 1, f"got {len(_pump_calls6)}")
with Session(_e6) as _s:
    _c6_after = _s.get(Chapter, _chs6[0])
    check("queued_at posé", _c6_after.queued_at is not None)


# ── 7. POST .../chapters/generate ("tout") : queued_at sur tous, pompe 1 fois
section("POST /books/{id}/chapters/generate -- queued_at sur tous les éligibles, pompe dispatchée UNE fois")
_e7 = _make_test_engine()
_bid7, _chs7 = _make_book_with_chapters(_e7, [["a"], ["b"], ["c"]], queue_all=False)
# Chapitre 2 déjà DONE -- ne doit pas être mis en file.
with Session(_e7) as _s:
    _c7b = _s.get(Chapter, _chs7[1])
    _c7b.status = ChapterStatus.DONE
    _s.add(_c7b)
    _s.commit()


def _session7():
    with Session(_e7) as s:
        yield s


app.dependency_overrides[get_session] = _session7
_pump_calls7 = []
books_module.generate_chapter_queue_pump = lambda: _pump_calls7.append(1)
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r7 = _tc.post(f"/books/{_bid7}/chapters/generate")
books_module.generate_chapter_queue_pump = generate_chapter_queue_pump  # restore
app.dependency_overrides.pop(get_session, None)

check("202", _r7.status_code == 202, f"got {_r7.status_code}: {_r7.text}")
check("pompe dispatchée UNE seule fois (pas 1 par chapitre)",
      len(_pump_calls7) == 1, f"got {len(_pump_calls7)}")
with Session(_e7) as _s:
    _c7a = _s.get(Chapter, _chs7[0])
    _c7b_after = _s.get(Chapter, _chs7[1])
    _c7c = _s.get(Chapter, _chs7[2])
    check("chapitre 1 (PENDING) mis en file", _c7a.queued_at is not None)
    check("chapitre 2 (déjà DONE) pas touché", _c7b_after.queued_at is None)
    check("chapitre 3 (PENDING) mis en file", _c7c.queued_at is not None)


# ── 8. GET /chapters/queue : ne montre que GENERATING + PENDING en file ─────
section("GET /chapters/queue -- omet un chapitre PENDING jamais demandé (queued_at=None)")
_e8 = _make_test_engine()
_bid8, _chs8 = _make_book_with_chapters(_e8, [["x"], ["y"]], queue_all=False)
# Chapitre 1 en file, chapitre 2 PENDING mais JAMAIS demandé.
with Session(_e8) as _s:
    _c8a = _s.get(Chapter, _chs8[0])
    _c8a.queued_at = datetime.now(timezone.utc)
    _s.add(_c8a)
    _s.commit()


def _session8():
    with Session(_e8) as s:
        yield s


app.dependency_overrides[get_session] = _session8
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r8 = _tc.get("/chapters/queue")
app.dependency_overrides.pop(get_session, None)

check("200", _r8.status_code == 200, f"got {_r8.status_code}: {_r8.text}")
_queue8 = _r8.json()
_positions8 = {item["position"] for item in _queue8 if item["book_id"] == _bid8}
check("chapitre 1 (en file) présent", 1 in _positions8, f"got {_positions8}")
check("chapitre 2 (jamais demandé) ABSENT de la file", 2 not in _positions8, f"got {_positions8}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p41.db", "huey_test_p41.db"):
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
