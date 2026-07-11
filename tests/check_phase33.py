"""check_phase33.py — Phase 33 : annulation d'une génération de chapitre en cours.

Contexte. Le /stop de niveau livre (Lot C, audit 2026-07-02) n'était jamais
branché sur la génération de chapitre standalone (_generate_chapter_impl) --
un chapitre marqué GENERATING via "Générer" (bouton unitaire, pas "Générer
l'audio" du livre entier) ne pouvait pas être interrompu : Huey revoke() ne
sert à rien ici, il n'annule qu'une tâche pas encore démarrée, jamais du code
déjà en cours d'exécution dans le worker. Ce lot ajoute Chapter.cancel_requested
(colonne bool, migration 9e2bc226e2fa) + _make_chapter_stop_checker, qui
réutilise le même mécanisme de polling devrait_abort() entre segments déjà
prouvé pour le niveau livre (_make_book_stop_checker / _synthesise_segments).

Valide :
  - _make_chapter_stop_checker() reflète Chapter.cancel_requested en base
    (fraîche à chaque appel, pas de session mise en cache).
  - _make_chapter_stop_checker() renvoie True si le chapitre a été supprimé
    entre-temps (mêmes garanties que le checker livre).
  - _generate_chapter_impl branche bien should_abort dans _generate_chapter_async
    -- un cancel_requested=True avant le 2e segment interrompt la synthèse,
    revient à PENDING, et cancel_requested est remis à False (pas de fuite
    d'état pour la prochaine tentative).
  - Régression : cancel_requested=False de bout en bout -> comportement
    inchangé (chapitre DONE, tous les segments synthétisés).

Run: .venv/Scripts/python tests/check_phase33.py
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p33.db",
    "HUEY_DB_PATH": "./huey_test_p33.db",
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
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.workers.tasks import _generate_chapter_impl, _make_chapter_stop_checker  # noqa: E402
ok("_generate_chapter_impl, _make_chapter_stop_checker, models, enums")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_chapter(engine, texts: list[str]):
    with Session(engine) as s:
        book = Book(title="P33Test", source_path="/tmp/x.epub")
        s.add(book)
        s.commit()
        s.refresh(book)
        ch = Chapter(book_id=book.id, position=1, title="Ch1", raw_text="x")
        s.add(ch)
        s.commit()
        s.refresh(ch)
        for pos, text in enumerate(texts, start=1):
            s.add(Segment(
                chapter_id=ch.id, position=pos, text=text,
                segment_type=SegmentType.NARRATION, character_id=None,
            ))
        s.commit()
        ch_id = ch.id
    return ch_id


def _make_book_with_chapters(engine, chapters_segments: list[list[str]]):
    """Crée un Book GENERATING avec N chapitres PENDING, chacun ayant les
    segments (textes) donnés. Retourne (book_id, [chapter_id, ...])."""
    with Session(engine) as s:
        book = Book(title="P33BookTest", source_path="/tmp/y.epub", status=BookStatus.GENERATING)
        s.add(book)
        s.commit()
        s.refresh(book)
        chapter_ids = []
        for i, texts in enumerate(chapters_segments, start=1):
            ch = Chapter(book_id=book.id, position=i, title=f"Ch{i}", raw_text="x")
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


class _CountingTTS:
    """Synthesise réussit toujours ; permet de déclencher cancel_requested=True
    entre deux segments en observant le compteur d'appels."""

    def __init__(self, on_call=None):
        self.calls = 0
        self._on_call = on_call

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        self.calls += 1
        if self._on_call:
            self._on_call(self.calls)
        return _make_wav_bytes(50)


# ── 2. _make_chapter_stop_checker reflète Chapter.cancel_requested en base ───
section("_make_chapter_stop_checker() reflète cancel_requested, relu à chaque appel")
_e2 = _make_test_engine()
_ch2 = _make_chapter(_e2, ["Un."])
_checker2 = _make_chapter_stop_checker(_e2, _ch2)
check("False par défaut (cancel_requested=False)", _checker2() is False)

with Session(_e2) as _s:
    _c = _s.get(Chapter, _ch2)
    _c.cancel_requested = True
    _s.add(_c)
    _s.commit()
check("True après passage de cancel_requested à True (pas de cache de session)", _checker2() is True)


# ── 3. _make_chapter_stop_checker renvoie True si le chapitre a disparu ──────
section("_make_chapter_stop_checker() renvoie True si le chapitre a été supprimé")
_e3 = _make_test_engine()
_checker3 = _make_chapter_stop_checker(_e3, 999999)  # id inexistant
check("True pour un chapter_id inconnu", _checker3() is True)


# ── 4. _generate_chapter_impl : cancel_requested interrompt et revient à PENDING
section("cancel_requested=True avant le 2e segment -> chapitre PENDING, cancel_requested remis à False")
_e4 = _make_test_engine()
_ch4 = _make_chapter(_e4, ["Segment1", "Segment2", "Segment3"])


def _cancel_after_first_call(n: int) -> None:
    if n == 1:
        with Session(_e4) as s:
            c = s.get(Chapter, _ch4)
            c.cancel_requested = True
            s.add(c)
            s.commit()


_tts4 = _CountingTTS(on_call=_cancel_after_first_call)

with (
    patch("app.core.db.get_engine", return_value=_e4),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts4),
):
    _generate_chapter_impl(_ch4)

check("1 seul segment synthétisé avant l'abandon (should_abort vérifié avant le 2e)",
      _tts4.calls == 1, f"got {_tts4.calls}")
with Session(_e4) as _s:
    _ch4_after = _s.get(Chapter, _ch4)
    check("chapitre revenu à PENDING (pas FAILED, pas DONE)",
          _ch4_after.status == ChapterStatus.PENDING, f"got {_ch4_after.status}")
    check("cancel_requested remis à False (pas de fuite d'état pour la prochaine tentative)",
          _ch4_after.cancel_requested is False)
    check("aucun audio_path persisté (rien à assembler pour un chapitre interrompu)",
          _ch4_after.audio_path is None)


# ── 5. Régression : cancel_requested=False de bout en bout -> DONE inchangé ──
section("Régression : cancel_requested jamais positionné -> chapitre DONE, tous les segments synthétisés")
_e5 = _make_test_engine()
_ch5 = _make_chapter(_e5, ["Segment1", "Segment2", "Segment3"])
_tts5 = _CountingTTS()

with (
    patch("app.core.db.get_engine", return_value=_e5),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts5),
):
    _generate_chapter_impl(_ch5)

check("3 segments synthétisés (aucune interruption)", _tts5.calls == 3, f"got {_tts5.calls}")
with Session(_e5) as _s:
    _ch5_after = _s.get(Chapter, _ch5)
    check("chapitre DONE", _ch5_after.status == ChapterStatus.DONE, f"got {_ch5_after.status}")
    check("audio_path renseigné", bool(_ch5_after.audio_path))


# ── 6. Génération pilotée par le livre : stop d'UN chapitre en cours ─────────
# (audit 2026-07-11) -- avant ce lot, _generate_book_async ne surveillait QUE
# Book.status (should_abort du niveau livre) ; Chapter.cancel_requested posé
# par POST /books/{id}/chapters/{n}/stop sur le chapitre EN COURS de synthèse
# pendant une génération de livre entier n'avait aucun effet : le chapitre se
# terminait normalement, et le flag résiduel avortait juste la PROCHAINE
# tentative standalone de ce chapitre au lieu de rien faire.
section("Génération livre : Chapter.cancel_requested du chapitre en cours interrompt le RUN entier")
_e6 = _make_test_engine()
_book6_id, _chs6 = _make_book_with_chapters(_e6, [["Segment1"], ["SegmentA", "SegmentB", "SegmentC"]])


def _cancel_chapter2_after_first_call(n: int) -> None:
    # Se déclenche pendant la synthèse du CHAPITRE 2 (son 1er segment,
    # 2e appel global) -- le chapitre 1 (1 seul segment) est déjà DONE ici.
    if n == 2:
        with Session(_e6) as s:
            c = s.get(Chapter, _chs6[1])
            c.cancel_requested = True
            s.add(c)
            s.commit()


_tts6 = _CountingTTS(on_call=_cancel_chapter2_after_first_call)

with (
    patch("app.core.db.get_engine", return_value=_e6),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts6),
):
    import asyncio as _asyncio6
    from app.workers.tasks import _generate_book_async
    _completed6 = _asyncio6.run(_generate_book_async(_book6_id, _e6))

check("_generate_book_async retourne False (abandon)", _completed6 is False, f"got {_completed6}")
check("2 segments synthétisés (chapitre 1 entier + 1er segment du chapitre 2)",
      _tts6.calls == 2, f"got {_tts6.calls}")
with Session(_e6) as _s:
    _ch6_1_after = _s.get(Chapter, _chs6[0])
    check("chapitre 1 DONE (terminé avant l'interruption)",
          _ch6_1_after.status == ChapterStatus.DONE, f"got {_ch6_1_after.status}")
    _ch6_2_after = _s.get(Chapter, _chs6[1])
    check("chapitre 2 revenu à PENDING (interrompu)",
          _ch6_2_after.status == ChapterStatus.PENDING, f"got {_ch6_2_after.status}")
    check("cancel_requested du chapitre 2 remis à False (pas de fuite d'état)",
          _ch6_2_after.cancel_requested is False)
    _book6_after = _s.get(Book, _book6_id)
    check("Book.status = FAILED (pas resté bloqué GENERATING pour toujours)",
          _book6_after.status == BookStatus.FAILED, f"got {_book6_after.status}")
    check("Book.error_message renseigné", bool(_book6_after.error_message))


# ── 7. cancel_requested résiduel nettoyé au DÉMARRAGE d'une génération ───────
# (audit 2026-07-11) -- scénario : un /stop cliqué juste après la synthèse du
# DERNIER segment d'un chapitre arrive trop tard pour interrompre quoi que ce
# soit (should_abort() n'est plus revérifié après le dernier segment) -- le
# chapitre finit DONE avec cancel_requested=True résiduel, puisque seul le
# chemin d'ABANDON remet le flag à False (jamais le chemin de succès). À la
# régénération standalone suivante de CE MÊME chapitre, le flag résiduel
# avorte la synthèse dès le premier segment -- une tentative fantôme perdue
# avant que la vraie génération ne puisse démarrer.
section("cancel_requested résiduel (d'un cycle précédent) nettoyé avant de démarrer -- pas d'avortement fantôme")
_e7 = _make_test_engine()
_ch7 = _make_chapter(_e7, ["Segment1", "Segment2"])
with Session(_e7) as _s:
    _c7 = _s.get(Chapter, _ch7)
    _c7.cancel_requested = True  # résidu d'un cycle précédent, jamais nettoyé
    _s.add(_c7)
    _s.commit()

_tts7 = _CountingTTS()

with (
    patch("app.core.db.get_engine", return_value=_e7),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts7),
):
    _generate_chapter_impl(_ch7)

check("2 segments synthétisés (pas d'avortement fantôme dès le 1er)",
      _tts7.calls == 2, f"got {_tts7.calls}")
with Session(_e7) as _s:
    _ch7_after = _s.get(Chapter, _ch7)
    check("chapitre DONE (le résidu n'a pas fait avorter cette tentative)",
          _ch7_after.status == ChapterStatus.DONE, f"got {_ch7_after.status}")
    check("cancel_requested toujours False après succès", _ch7_after.cancel_requested is False)


# ── Résumé ───────────────────────────────────────────────────────────────────
print()
if _errors:
    print(f"{FAIL} — {len(_errors)} échec(s) sur {_n} sections")
    sys.exit(1)
else:
    print(f"{PASS} — {_n} sections passées")
