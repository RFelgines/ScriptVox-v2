"""check_phase39.py — Phase 39 (audit 2026-07-11) : gardes /generate sur une
analyse incomplète.

Contexte : POST /books/{id}/generate accepte le statut FAILED (pour reprendre
une génération interrompue par /stop ou une vraie panne TTS, Lot C audit
2026-07-02) sans jamais vérifier que l'ANALYSE, elle, a bien produit des
segments pour chaque chapitre. Deux scénarios réels :

  1. EPUB corrompu -> EpubParsingError avant même la création du moindre
     chapitre -> book FAILED, ZÉRO chapitre. "Générer" était accepté ->
     _generate_book_async voyait total=0 -> `return True` -> le livre
     finissait DONE, progress=100, audio_path=None : un mensonge d'état.
  2. Analyse LLM interrompue à mi-parcours (stop, crash, timeout définitif)
     -> book FAILED, chapitres tous créés (ingestion EPUB = un seul batch)
     mais seuls les premiers ont des segments. "Générer" échouait alors en
     synthèse avec un ValueError cryptique ("Chapter N has no segments to
     synthesise") au lieu d'orienter vers "reprendre l'analyse".

Valide :
  - POST /generate sur un livre FAILED SANS aucun chapitre -> 409, aucun
    dispatch Huey.
  - POST /generate sur un livre FAILED avec des chapitres dont au moins un
    n'a aucun segment -> 409 mentionnant le(s) chapitre(s) concerné(s), aucun
    dispatch.
  - Régression : POST /generate sur un livre ANALYZED dont TOUS les chapitres
    ont des segments -> 202 + dispatch (comportement inchangé).
  - Défense en profondeur : _generate_book_impl appelé directement (hors
    route) sur un livre à 0 chapitre -> le livre finit FAILED (jamais DONE
    avec audio_path=None), error_message renseigné.

Run: .venv/Scripts/python tests/check_phase39.py
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p39.db",
    "HUEY_DB_PATH": "./huey_test_p39.db",
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
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import get_session  # noqa: E402
from app.core.enums import BookStatus, SegmentType  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
ok("app, get_session, Book, Chapter, Segment")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


# ── 2. 0 chapitre (EPUB corrompu) -> 409, aucun dispatch ─────────────────────
section("POST /generate -- livre FAILED sans aucun chapitre -> 409, aucun dispatch")
_e2 = _make_test_engine()
with Session(_e2) as _s:
    _book2 = Book(title="EPUB corrompu", source_path="/tmp/x.epub", status=BookStatus.FAILED)
    _s.add(_book2)
    _s.commit()
    _book2_id = _book2.id


def _override_session_2():
    with Session(_e2) as s:
        yield s


app.dependency_overrides[get_session] = _override_session_2
with patch("app.api.routes.books.generate_book") as _mock_gen2:
    with TestClient(app, raise_server_exceptions=False) as tc:
        _r2 = tc.post(f"/books/{_book2_id}/generate")
check("409", _r2.status_code == 409, f"got {_r2.status_code}: {_r2.text}")
check("aucun dispatch generate_book", not _mock_gen2.called)
app.dependency_overrides.pop(get_session, None)


# ── 3. Chapitres présents mais un sans segment -> 409 mentionnant le chapitre ─
section("POST /generate -- analyse incomplète (chapitre sans segment) -> 409, aucun dispatch")
_e3 = _make_test_engine()
with Session(_e3) as _s:
    _book3 = Book(title="Analyse interrompue", source_path="/tmp/y.epub", status=BookStatus.FAILED)
    _s.add(_book3)
    _s.commit()
    _book3_id = _book3.id
    _ch3a = Chapter(book_id=_book3_id, position=1, raw_text="Chapitre un.")
    _ch3b = Chapter(book_id=_book3_id, position=2, raw_text="Chapitre deux jamais analysé.")
    _s.add(_ch3a)
    _s.add(_ch3b)
    _s.commit()
    _s.refresh(_ch3a)
    _s.add(Segment(chapter_id=_ch3a.id, position=1, text="Chapitre un.", segment_type=SegmentType.NARRATION))
    _s.commit()


def _override_session_3():
    with Session(_e3) as s:
        yield s


app.dependency_overrides[get_session] = _override_session_3
with patch("app.api.routes.books.generate_book") as _mock_gen3:
    with TestClient(app, raise_server_exceptions=False) as tc:
        _r3 = tc.post(f"/books/{_book3_id}/generate")
check("409", _r3.status_code == 409, f"got {_r3.status_code}: {_r3.text}")
check("détail mentionne le chapitre 2", "2" in _r3.text, _r3.text)
check("aucun dispatch generate_book", not _mock_gen3.called)
app.dependency_overrides.pop(get_session, None)


# ── 4. Régression : analyse complète -> 202 + dispatch (inchangé) ────────────
section("Régression : POST /generate -- tous les chapitres ont des segments -> 202 + dispatch")
_e4 = _make_test_engine()
with Session(_e4) as _s:
    _book4 = Book(title="Livre complet", source_path="/tmp/z.epub", status=BookStatus.ANALYZED)
    _s.add(_book4)
    _s.commit()
    _book4_id = _book4.id
    _ch4a = Chapter(book_id=_book4_id, position=1, raw_text="Un.")
    _ch4b = Chapter(book_id=_book4_id, position=2, raw_text="Deux.")
    _s.add(_ch4a)
    _s.add(_ch4b)
    _s.commit()
    _s.refresh(_ch4a)
    _s.refresh(_ch4b)
    _s.add(Segment(chapter_id=_ch4a.id, position=1, text="Un.", segment_type=SegmentType.NARRATION))
    _s.add(Segment(chapter_id=_ch4b.id, position=1, text="Deux.", segment_type=SegmentType.NARRATION))
    _s.commit()


def _override_session_4():
    with Session(_e4) as s:
        yield s


app.dependency_overrides[get_session] = _override_session_4
with patch("app.api.routes.books.generate_book") as _mock_gen4:
    with TestClient(app, raise_server_exceptions=False) as tc:
        _r4 = tc.post(f"/books/{_book4_id}/generate")
check("202", _r4.status_code == 202, f"got {_r4.status_code}: {_r4.text}")
check("generate_book dispatché une fois", _mock_gen4.call_count == 1)
app.dependency_overrides.pop(get_session, None)


# ── 5. Défense en profondeur : _generate_book_impl direct, 0 chapitre ───────
section("_generate_book_impl (hors route) sur 0 chapitre -> FAILED, jamais DONE")
_e5 = _make_test_engine()
with Session(_e5) as _s:
    _book5 = Book(title="Vide", source_path="/tmp/w.epub", status=BookStatus.FAILED)
    _s.add(_book5)
    _s.commit()
    _book5_id = _book5.id

with patch("app.core.db.get_engine", return_value=_e5):
    from app.workers.tasks import _generate_book_impl  # noqa: E402
    _generate_book_impl(_book5_id)

with Session(_e5) as _s:
    _book5_after = _s.get(Book, _book5_id)
    check("statut FAILED (jamais DONE)", _book5_after.status == BookStatus.FAILED,
          f"got {_book5_after.status}")
    check("audio_path resté vide", _book5_after.audio_path is None)
    check("error_message renseigné", bool(_book5_after.error_message))


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p39.db", "huey_test_p39.db"):
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
