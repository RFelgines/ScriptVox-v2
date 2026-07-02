"""check_phase23.py — Phase 23 (Lot A, audit 2026-07-02) : honorer /stop.

Valide que `POST /books/{id}/stop` (qui pose Book.status=FAILED en DB) n'est plus
écrasé par la fin de l'analyse ou de la génération :
  - A1a : stop pendant la boucle de chapitres -> chapitres restants sans segment,
          status reste FAILED (pas ANALYZED), voice_id jamais assigné.
  - A1b : stop juste avant suggest_merges -> suggest_merges jamais appelé.
  - A2  : stop pendant la boucle TTS -> segments restants jamais synthétisés,
          status reste FAILED (pas DONE), audio_path jamais écrit.

Run: .venv/Scripts/python tests/check_phase23.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE_EPUB = ROOT / "tests" / "fixtures" / "test.epub"

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p23.db",
    "HUEY_DB_PATH": "./huey_test_p23.db",
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

from app.core.enums import BookStatus, Gender, SegmentType  # noqa: E402
from app.models import Book, Chapter, Character, Segment  # noqa: E402
from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData  # noqa: E402
from app.workers.tasks import _analyze_book_impl, _generate_book_impl  # noqa: E402
ok("_analyze_book_impl, _generate_book_impl, models, enums, LLM dataclasses")


# ── 2. Fixture EPUB présente (3 chapitres attendus) ───────────────────────────
section("Fixture EPUB présente")
if not FIXTURE_EPUB.exists():
    fail("Fixture manquante", str(FIXTURE_EPUB))
    print(f"\n{FAIL} impossible de continuer sans fixture")
    sys.exit(1)
ok(f"Trouvée : {FIXTURE_EPUB.name}")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _simulate_user_stop(engine, book_id: int) -> None:
    """Reproduit exactement l'effet de POST /books/{id}/stop (books.py trigger_stop)."""
    with Session(engine) as s:
        b = s.get(Book, book_id)
        b.status = BookStatus.FAILED
        b.error_message = "Arrêté par l'utilisateur."
        s.add(b)
        s.commit()


# ── 3. A1a — stop en cours de boucle de chapitres ─────────────────────────────
section("A1a: stop pendant la boucle d'analyse -> chapitres suivants sans segment, status=FAILED")


class _StopMidLoopLLM:
    """Simule un /stop concurrent déclenché pendant l'analyse du 1er chapitre :
    le 1er appel analyze() se termine normalement, MAIS le statut devient FAILED
    avant que la boucle n'attaque le chapitre suivant."""

    def __init__(self, engine, book_id: int) -> None:
        self._engine = engine
        self._book_id = book_id
        self.calls = 0

    async def analyze(self, text: str, known_characters=None) -> LLMChapterResult:
        self.calls += 1
        if self.calls == 1:
            _simulate_user_stop(self._engine, self._book_id)
        return LLMChapterResult(
            characters=[CharacterData(name="Alice", description=None, gender=Gender.FEMALE)],
            segments=[SegmentData(
                position=1, text="Bonjour.",
                segment_type=SegmentType.NARRATION, character_name=None,
            )],
        )

    async def suggest_merges(self, characters):
        return []


_e3 = _make_test_engine()
with Session(_e3) as _s:
    _b3 = Book(title="StopMidLoop", source_path=str(FIXTURE_EPUB))
    _s.add(_b3)
    _s.commit()
    _s.refresh(_b3)
    _b3_id = _b3.id

_llm3 = _StopMidLoopLLM(_e3, _b3_id)
with (
    patch("app.core.db.get_engine", return_value=_e3),
    patch("app.services.llm.factory.get_llm_provider", return_value=_llm3),
):
    _analyze_book_impl(_b3_id)

with Session(_e3) as _s:
    _b3_after = _s.get(Book, _b3_id)
    check("analyze() appelé une seule fois (chapitre 1 seulement)", _llm3.calls == 1,
          f"got {_llm3.calls}")
    check("status reste FAILED (pas ANALYZED)", _b3_after.status == BookStatus.FAILED,
          f"got {_b3_after.status}")
    check("error_message préservé (pas écrasé par la suite du pipeline)",
          _b3_after.error_message == "Arrêté par l'utilisateur.",
          f"got {_b3_after.error_message!r}")

    _chapters3 = _s.exec(
        select(Chapter).where(Chapter.book_id == _b3_id).order_by(Chapter.position)
    ).all()
    check("3 chapitres présents (EPUB ingéré avant l'abandon)", len(_chapters3) == 3,
          f"got {len(_chapters3)}")
    for _ch in _chapters3:
        _segs = _s.exec(select(Segment).where(Segment.chapter_id == _ch.id)).all()
        if _ch.position == 1:
            check(f"chapitre 1 a des segments (analysé avant le stop)", len(_segs) > 0,
                  f"got {len(_segs)}")
        else:
            check(f"chapitre {_ch.position} n'a AUCUN segment (jamais atteint)", len(_segs) == 0,
                  f"got {len(_segs)}")

    _chars3 = _s.exec(select(Character).where(Character.book_id == _b3_id)).all()
    check("personnage 'Alice' créé (chapitre 1 traité)",
          any(c.name == "Alice" for c in _chars3))
    check("voice_id jamais assigné (assign_voices n'a pas tourné, pipeline abandonné)",
          all(c.voice_id is None for c in _chars3),
          f"got {[(c.name, c.voice_id) for c in _chars3]}")


# ── 4. A1b — stop juste avant suggest_merges ──────────────────────────────────
section("A1b: stop entre la fin des chapitres et suggest_merges -> jamais appelé")


class _StopBeforeMergeLLM:
    """Les 3 chapitres sont analysés normalement (3 personnages distincts pour
    déclencher la branche suggest_merges), mais le statut devient FAILED au
    moment où le dernier chapitre termine -- avant l'appel à suggest_merges."""

    _NAMES = {1: "Alice", 2: "Bob", 3: "Carol"}

    def __init__(self, engine, book_id: int) -> None:
        self._engine = engine
        self._book_id = book_id
        self.calls = 0
        self.suggest_calls = 0

    async def analyze(self, text: str, known_characters=None) -> LLMChapterResult:
        self.calls += 1
        name = self._NAMES[self.calls]
        if self.calls == 3:
            _simulate_user_stop(self._engine, self._book_id)
        return LLMChapterResult(
            characters=[CharacterData(name=name, description=None, gender=Gender.FEMALE)],
            segments=[SegmentData(
                position=1, text=f"{name} parle.",
                segment_type=SegmentType.NARRATION, character_name=None,
            )],
        )

    async def suggest_merges(self, characters):
        self.suggest_calls += 1
        return []


_e4 = _make_test_engine()
with Session(_e4) as _s:
    _b4 = Book(title="StopBeforeMerge", source_path=str(FIXTURE_EPUB))
    _s.add(_b4)
    _s.commit()
    _s.refresh(_b4)
    _b4_id = _b4.id

_llm4 = _StopBeforeMergeLLM(_e4, _b4_id)
with (
    patch("app.core.db.get_engine", return_value=_e4),
    patch("app.services.llm.factory.get_llm_provider", return_value=_llm4),
):
    _analyze_book_impl(_b4_id)

with Session(_e4) as _s:
    _b4_after = _s.get(Book, _b4_id)
    check("les 3 chapitres ont été analysés", _llm4.calls == 3, f"got {_llm4.calls}")
    check("suggest_merges JAMAIS appelé (stop détecté avant)", _llm4.suggest_calls == 0,
          f"got {_llm4.suggest_calls}")
    check("status reste FAILED (pas ANALYZED)", _b4_after.status == BookStatus.FAILED,
          f"got {_b4_after.status}")

    _chars4 = _s.exec(select(Character).where(Character.book_id == _b4_id)).all()
    check("3 personnages créés (Alice, Bob, Carol)",
          {c.name for c in _chars4} == {"Alice", "Bob", "Carol"},
          f"got {[c.name for c in _chars4]}")
    check("voice_id jamais assigné", all(c.voice_id is None for c in _chars4),
          f"got {[(c.name, c.voice_id) for c in _chars4]}")


# ── 5. A2 — stop en cours de génération TTS ───────────────────────────────────
section("A2: stop pendant la boucle TTS -> segments restants jamais synthétisés, status=FAILED")


class _StopMidTTSLoop:
    """Le 1er appel synthesise() se termine normalement, MAIS simule un /stop
    concurrent avant que la boucle n'attaque le segment suivant."""

    def __init__(self, engine, book_id: int) -> None:
        self._engine = engine
        self._book_id = book_id
        self.calls = 0

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        self.calls += 1
        if self.calls == 1:
            _simulate_user_stop(self._engine, self._book_id)
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 50)
        return buf.getvalue()


_e5 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp5:
    # source_path n'a pas besoin d'être un EPUB réel ici (_generate_book_impl ne
    # re-parse jamais l'EPUB) -- un chemin dans un tempdir évite juste que
    # assemble_wav() (si jamais atteint, ce qu'on veut prouver que non) n'écrive
    # à côté des fixtures versionnées du dépôt.
    _b5_source = str(Path(_tmp5) / "stop_mid_tts.epub")

    with Session(_e5) as _s:
        _b5 = Book(
            title="StopMidTTS", source_path=_b5_source, status=BookStatus.ANALYZED,
        )
        _s.add(_b5)
        _s.commit()
        _s.refresh(_b5)
        _b5_id = _b5.id

        _ch5 = Chapter(book_id=_b5_id, position=1, title="Ch1", raw_text="peu importe")
        _s.add(_ch5)
        _s.commit()
        _s.refresh(_ch5)

        for _pos in range(1, 5):
            _s.add(Segment(
                chapter_id=_ch5.id, position=_pos, text=f"Segment {_pos}.",
                segment_type=SegmentType.NARRATION, character_id=None,
            ))
        _s.commit()

    _tts5 = _StopMidTTSLoop(_e5, _b5_id)
    with (
        patch("app.core.db.get_engine", return_value=_e5),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts5),
    ):
        _generate_book_impl(_b5_id)

    with Session(_e5) as _s:
        _b5_after = _s.get(Book, _b5_id)
        check("synthesise() appelé une seule fois (1 seul segment sur 4)", _tts5.calls == 1,
              f"got {_tts5.calls}")
        check("status reste FAILED (pas DONE)", _b5_after.status == BookStatus.FAILED,
              f"got {_b5_after.status}")
        check("audio_path jamais écrit", _b5_after.audio_path is None,
              f"got {_b5_after.audio_path!r}")
        check("mp3_path jamais écrit", _b5_after.mp3_path is None,
              f"got {_b5_after.mp3_path!r}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p23.db", "huey_test_p23.db"):
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
