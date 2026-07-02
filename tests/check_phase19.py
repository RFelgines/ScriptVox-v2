"""check_phase19.py — Phase 19 : reprise d'analyse après arrêt/plantage.

`_analyze_book_impl(book_id, force=False)` distingue désormais 3 cas selon le statut
du livre *avant* l'appel :
  - FAILED + force=False -> reprise : pas de re-parse EPUB, saute les chapitres qui ont
    déjà des segments, repart des personnages déjà en base.
  - PENDING, ou FAILED + force=True, ou ANALYZED/DONE -> comportement inchangé (purge +
    re-parse EPUB + ré-analyse complète).

Run: .venv/Scripts/python tests/check_phase19.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE_EPUB = ROOT / "tests" / "fixtures" / "test.epub"

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p19.db",
    "HUEY_DB_PATH": "./huey_test_p19.db",
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


# ── 1. Signatures ─────────────────────────────────────────────────────────────
section("Signatures : analyze_book/_analyze_book_impl(force=False), _analyze_book(resume=False)")
import inspect  # noqa: E402

from app.workers.tasks import _analyze_book, _analyze_book_impl, analyze_book  # noqa: E402

sig_impl = inspect.signature(_analyze_book_impl)
check("'force' présent sur _analyze_book_impl", "force" in sig_impl.parameters)
check("défaut force=False", sig_impl.parameters["force"].default is False)

# analyze_book est décoré @huey.task() -> .func conserve la signature Python d'origine
sig_task = inspect.signature(getattr(analyze_book, "func", analyze_book))
check("'force' présent sur la tâche Huey analyze_book", "force" in sig_task.parameters)

sig_ab = inspect.signature(_analyze_book)
check("'resume' présent sur _analyze_book", "resume" in sig_ab.parameters)
check("défaut resume=False", sig_ab.parameters["resume"].default is False)
check("'already_done' présent sur _analyze_book", "already_done" in sig_ab.parameters)


# ── 2. _analyze_book : resume=True préserve les Character existants ─────────
section("_analyze_book(resume=True) : ne wipe pas les Character, char_map reconstruit depuis la DB")

import asyncio  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.enums import Gender, SegmentType  # noqa: E402
from app.models import Book, Character, Chapter, Segment  # noqa: E402
from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData  # noqa: E402
import app.services.llm.factory as llm_factory  # noqa: E402

_engine2 = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine2)

with Session(_engine2) as _s:
    _book2 = Book(title="Resume2", source_path="/tmp/r2.epub")
    _s.add(_book2)
    _s.commit()
    _book2_id = _book2.id

    _existing_char = Character(book_id=_book2_id, name="Alice", gender=Gender.FEMALE)
    _s.add(_existing_char)
    _s.commit()
    _existing_char_id = _existing_char.id


class _Recorder2:
    def __init__(self) -> None:
        self.calls: list[list[str] | None] = []

    async def analyze(
        self, text: str, known_characters: list[str] | None = None,
        language: str | None = None,
    ) -> LLMChapterResult:
        self.calls.append(known_characters)
        return LLMChapterResult(
            characters=[CharacterData(name="Bob", description=None, gender=Gender.MALE)],
            segments=[SegmentData(
                position=1, text=text or "x",
                segment_type=SegmentType.NARRATION, character_name=None,
            )],
        )

    async def suggest_merges(self, characters):
        return []


_orig_get_provider = llm_factory.get_llm_provider
_rec2 = _Recorder2()
llm_factory.get_llm_provider = lambda settings: _rec2
try:
    asyncio.run(_analyze_book(_book2_id, [(999, "Chapitre restant.")], _engine2, resume=True))
finally:
    llm_factory.get_llm_provider = _orig_get_provider

check("known_characters reçu == ['Alice'] (char_map reconstruit depuis la DB)",
      _rec2.calls and _rec2.calls[0] == ["Alice"], f"got {_rec2.calls!r}")

with Session(_engine2) as _s:
    _chars2 = _s.exec(select(Character).where(Character.book_id == _book2_id)).all()
check("Alice (préexistant) + Bob (nouveau) -> 2 Character, Alice non supprimée",
      {c.name for c in _chars2} == {"Alice", "Bob"}, f"got {[c.name for c in _chars2]}")
check("l'id du Character Alice préexistant est inchangé",
      any(c.id == _existing_char_id and c.name == "Alice" for c in _chars2))

_engine2.dispose()


# ── 3. Pipeline réel _analyze_book_impl : reprise après arrêt ────────────────
section("_analyze_book_impl : reprise -- saute les chapitres déjà segmentés, pas de re-parse EPUB")

from app.core.enums import BookStatus  # noqa: E402
from app.services.epub.parser import EpubParser  # noqa: E402

_engine3 = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine3)

with Session(_engine3) as _s:
    _book3 = Book(
        title="Interrupted", source_path="/tmp/does_not_matter.epub",
        status=BookStatus.FAILED, error_message="Arrêté par l'utilisateur.",
    )
    _s.add(_book3)
    _s.commit()
    _book3_id = _book3.id

    # Chapitre 1 : déjà analysé (a un Character + un Segment)
    _ch1 = Chapter(book_id=_book3_id, position=1, title="Ch1", raw_text="Texte du chapitre 1.")
    _s.add(_ch1)
    _s.commit()
    _alice = Character(book_id=_book3_id, name="Alice", gender=Gender.FEMALE)
    _s.add(_alice)
    _s.commit()
    _s.add(Segment(
        chapter_id=_ch1.id, position=1, text="Texte déjà analysé.",
        segment_type=SegmentType.NARRATION,
    ))
    _s.commit()
    _ch1_id = _ch1.id
    _ch1_segment_ids = [
        seg.id for seg in _s.exec(select(Segment).where(Segment.chapter_id == _ch1_id)).all()
    ]

    # Chapitres 2 et 3 : pas encore analysés (existent mais sans segment)
    _ch2 = Chapter(book_id=_book3_id, position=2, title="Ch2", raw_text="Texte du chapitre 2.")
    _ch3 = Chapter(book_id=_book3_id, position=3, title="Ch3", raw_text="Texte du chapitre 3.")
    _s.add(_ch2)
    _s.add(_ch3)
    _s.commit()


class _Recorder3:
    def __init__(self) -> None:
        self.calls: list[list[str] | None] = []

    async def analyze(
        self, text: str, known_characters: list[str] | None = None,
        language: str | None = None,
    ) -> LLMChapterResult:
        self.calls.append(known_characters)
        return LLMChapterResult(
            characters=[CharacterData(name="Bob", description=None, gender=Gender.MALE)],
            segments=[SegmentData(
                position=1, text=text or "x",
                segment_type=SegmentType.NARRATION, character_name=None,
            )],
        )

    async def suggest_merges(self, characters):
        return []


_rec3 = _Recorder3()
_mock_epub_parse = MagicMock(side_effect=AssertionError("EpubParser.parse NE DOIT PAS être appelé en reprise"))

with (
    patch("app.core.db.get_engine", return_value=_engine3),
    patch("app.services.llm.factory.get_llm_provider", return_value=_rec3),
    patch.object(EpubParser, "parse", _mock_epub_parse),
):
    _analyze_book_impl(_book3_id)

check("2 appels LLM (chapitres 2 et 3 seulement, chapitre 1 sauté)",
      len(_rec3.calls) == 2, f"got {len(_rec3.calls)}")
check("1er appel resté -> known_characters == ['Alice'] (repris de la DB)",
      _rec3.calls and _rec3.calls[0] == ["Alice"], f"got {_rec3.calls!r}")

with Session(_engine3) as _s:
    _b3 = _s.get(Book, _book3_id)
    check("status == ANALYZED après reprise", _b3.status == BookStatus.ANALYZED,
          f"got {_b3.status}, error={_b3.error_message!r}")
    check("progress == 100.0", _b3.progress == 100.0, f"got {_b3.progress}")

    _ch1_segs_after = _s.exec(select(Segment).where(Segment.chapter_id == _ch1_id)).all()
    check("segment du chapitre 1 (déjà fait) inchangé (même id, même texte)",
          [s.id for s in _ch1_segs_after] == _ch1_segment_ids
          and _ch1_segs_after[0].text == "Texte déjà analysé.",
          f"got ids={[s.id for s in _ch1_segs_after]} text={[s.text for s in _ch1_segs_after]}")

    _chars3 = _s.exec(select(Character).where(Character.book_id == _book3_id)).all()
    check("Alice (préexistante) toujours là + Bob (nouveau)",
          {c.name for c in _chars3} == {"Alice", "Bob"}, f"got {[c.name for c in _chars3]}")

_engine3.dispose()


# ── 4. Pipeline réel _analyze_book_impl : force=True ignore la reprise ───────
section("_analyze_book_impl(force=True) : purge tout + re-parse EPUB malgré FAILED")

if not FIXTURE_EPUB.exists():
    fail("fixture epub manquante", str(FIXTURE_EPUB))
else:
    _engine4 = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(_engine4)

    with tempfile.TemporaryDirectory() as _tmp4:
        _epub4 = Path(_tmp4) / "test.epub"
        shutil.copy(FIXTURE_EPUB, _epub4)

        with Session(_engine4) as _s:
            _book4 = Book(
                title="WillForceRestart", source_path=str(_epub4),
                status=BookStatus.FAILED, error_message="Une vraie erreur LLM.",
            )
            _s.add(_book4)
            _s.commit()
            _book4_id = _book4.id

            _ch1_4 = Chapter(book_id=_book4_id, position=1, title="Old", raw_text="Vieux texte.")
            _s.add(_ch1_4)
            _s.commit()
            _alice4 = Character(book_id=_book4_id, name="OldChar", gender=Gender.FEMALE)
            _s.add(_alice4)
            _s.commit()
            _s.add(Segment(
                chapter_id=_ch1_4.id, position=1, text="Vieux segment.",
                segment_type=SegmentType.NARRATION,
            ))
            _s.commit()

        class _Recorder4:
            def __init__(self) -> None:
                self.calls = 0

            async def analyze(
                self, text: str, known_characters: list[str] | None = None,
                language: str | None = None,
            ) -> LLMChapterResult:
                self.calls += 1
                return LLMChapterResult(
                    characters=[CharacterData(name="FreshChar", description=None, gender=Gender.MALE)],
                    segments=[SegmentData(
                        position=1, text=text or "x",
                        segment_type=SegmentType.NARRATION, character_name=None,
                    )],
                )

            async def suggest_merges(self, characters):
                return []

        _rec4 = _Recorder4()
        with (
            patch("app.core.db.get_engine", return_value=_engine4),
            patch("app.services.llm.factory.get_llm_provider", return_value=_rec4),
        ):
            _analyze_book_impl(_book4_id, force=True)

        check("EpubParser réellement appelé (3 chapitres de la fixture re-créés)",
              _rec4.calls == 3, f"got {_rec4.calls} appels LLM")

        with Session(_engine4) as _s:
            _b4 = _s.get(Book, _book4_id)
            check("status == ANALYZED", _b4.status == BookStatus.ANALYZED,
                  f"got {_b4.status}, error={_b4.error_message!r}")

            _chars4 = _s.exec(select(Character).where(Character.book_id == _book4_id)).all()
            check("ancien personnage 'OldChar' supprimé (purge complète)",
                  "OldChar" not in {c.name for c in _chars4}, f"got {[c.name for c in _chars4]}")
            check("nouveau personnage 'FreshChar' présent",
                  "FreshChar" in {c.name for c in _chars4}, f"got {[c.name for c in _chars4]}")

    _engine4.dispose()


# ── Cleanup ───────────────────────────────────────────────────────────────────
for leftover in ("scriptvox_test_p19.db", "huey_test_p19.db"):
    if os.path.exists(leftover):
        os.remove(leftover)


# ── Résumé ────────────────────────────────────────────────────────────────────
print(f"\n{'='*52}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
