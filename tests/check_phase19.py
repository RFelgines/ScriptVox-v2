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
llm_factory.get_llm_provider = lambda settings, override=None: _rec2
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


# ── 5. Réconciliation des zombies au démarrage du worker (audit 2026-07-11) ──
# Sections 1-4 ci-dessus couvrent la reprise EXPLICITE (l'utilisateur clique
# "Reprendre") après un /stop ou une vraie erreur -- mais un kill/reboot du
# process worker en PLEIN milieu d'une tâche (Ctrl+C sur le consumer Huey,
# geste banal en local) ne déclenche RIEN de tout ça : SqliteHuey ne rejoue
# jamais une tâche déjà consommée, donc Book.status reste PROCESSING/GENERATING
# et Chapter.status reste GENERATING pour toujours -- un livre récupérable par
# un détour non documenté (/stop accepte PROCESSING/GENERATING même worker
# mort), un chapitre standalone sans AUCUNE issue (regénérer -> 409, stop pose
# un flag que plus personne ne relit). _reconcile_zombie_state (@huey.on_startup)
# balaie cet état au (re)démarrage du worker -- à cet instant précis, avec un
# seul worker pour toute l'app, rien ne peut légitimement être "en cours".
section("_reconcile_zombie_state (@huey.on_startup) : balaie PROCESSING/GENERATING au (re)démarrage")

from app.workers.tasks import _reconcile_zombie_state, huey  # noqa: E402
from app.core.enums import ChapterStatus  # noqa: E402

_engine5 = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine5)

with Session(_engine5) as _s:
    _book5a = Book(title="Zombie analyse", source_path="/tmp/a.epub", status=BookStatus.PROCESSING)
    _book5b = Book(title="Zombie génération", source_path="/tmp/b.epub", status=BookStatus.GENERATING)
    _book5c = Book(title="Terminé, à ne pas toucher", source_path="/tmp/c.epub", status=BookStatus.DONE)
    _s.add(_book5a)
    _s.add(_book5b)
    _s.add(_book5c)
    _s.commit()
    _book5a_id, _book5b_id, _book5c_id = _book5a.id, _book5b.id, _book5c.id

    _ch5_zombie = Chapter(
        book_id=_book5b_id, position=1, title="En cours", raw_text="x",
        status=ChapterStatus.GENERATING, cancel_requested=True,
    )
    _ch5_done = Chapter(
        book_id=_book5c_id, position=1, title="Fini", raw_text="x",
        status=ChapterStatus.DONE, audio_path="/data/1/ch1.wav",
    )
    _s.add(_ch5_zombie)
    _s.add(_ch5_done)
    _s.commit()
    _ch5_zombie_id, _ch5_done_id = _ch5_zombie.id, _ch5_done.id

with patch("app.core.db.get_engine", return_value=_engine5):
    _reconcile_zombie_state()

with Session(_engine5) as _s:
    _b5a = _s.get(Book, _book5a_id)
    check("Book PROCESSING -> FAILED", _b5a.status == BookStatus.FAILED, f"got {_b5a.status}")
    check("Book PROCESSING -> error_message renseigné", bool(_b5a.error_message))

    _b5b = _s.get(Book, _book5b_id)
    check("Book GENERATING -> FAILED", _b5b.status == BookStatus.FAILED, f"got {_b5b.status}")

    _b5c = _s.get(Book, _book5c_id)
    check("Book DONE non touché", _b5c.status == BookStatus.DONE, f"got {_b5c.status}")

    _c5z = _s.get(Chapter, _ch5_zombie_id)
    check("Chapter GENERATING -> PENDING", _c5z.status == ChapterStatus.PENDING, f"got {_c5z.status}")
    check("Chapter cancel_requested résiduel remis à False",
          _c5z.cancel_requested is False, f"got {_c5z.cancel_requested}")

    _c5d = _s.get(Chapter, _ch5_done_id)
    check("Chapter DONE non touché (audio_path intact)",
          _c5d.status == ChapterStatus.DONE and _c5d.audio_path == "/data/1/ch1.wav",
          f"got status={_c5d.status} audio_path={_c5d.audio_path!r}")

check("_reconcile_zombie_state enregistrée comme hook huey.on_startup",
      "_reconcile_zombie_state" in getattr(huey, "_startup", {}), f"got {list(getattr(huey, '_startup', {}))}")

_engine5.dispose()


# ── 6. Retry LLM réussi -> error_message nettoyé (audit 2026-07-11) ──────────
# Le message "[ch X/Y essai Z/3] ... nouvel essai dans 30s" écrit entre deux
# tentatives (ARCHITECTURE.md §2.5) n'était jamais effacé si la tentative
# suivante réussissait : le livre finissait ANALYZED avec un error_message
# de progression périmé exposé par l'API.
section("Retry LLM réussi (essai 2/3) -> error_message nettoyé, pas de message résiduel")

import app.workers.tasks as _tasks_mod  # noqa: E402


async def _instant_sleep6(*_a, **_kw) -> None:
    return None


class _FlakyOnceProvider6:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, text, known_characters=None, language=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Panne LLM transitoire simulée")
        return LLMChapterResult(
            characters=[CharacterData(name="Eve", description=None, gender=Gender.FEMALE)],
            segments=[SegmentData(
                position=1, text=text or "x",
                segment_type=SegmentType.NARRATION, character_name=None,
            )],
        )

    async def suggest_merges(self, characters):
        return []


_engine6 = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine6)

with Session(_engine6) as _s:
    _book6 = Book(title="Retry6", source_path="/tmp/retry6.epub")
    _s.add(_book6)
    _s.commit()
    _book6_id = _book6.id

_rec6 = _FlakyOnceProvider6()
_orig_get_provider6 = llm_factory.get_llm_provider
llm_factory.get_llm_provider = lambda settings, override=None: _rec6
try:
    with patch.object(_tasks_mod.asyncio, "sleep", side_effect=_instant_sleep6):
        _completed6b = asyncio.run(_analyze_book(_book6_id, [(1, "Un chapitre.")], _engine6))
finally:
    llm_factory.get_llm_provider = _orig_get_provider6

check("2 appels LLM (1 échec + 1 succès)", _rec6.calls == 2, f"got {_rec6.calls}")
check("_analyze_book retourne True", _completed6b is True)
with Session(_engine6) as _s:
    _b6 = _s.get(Book, _book6_id)
    check("error_message nettoyé après le retry réussi (pas de message résiduel)",
          _b6.error_message is None, f"got {_b6.error_message!r}")

_engine6.dispose()


# ── 7. Reprise d'analyse -> suggestions de fusion PAS dupliquées ─────────────
# (audit 2026-07-11) -- la purge de CharacterMergeSuggestion n'existait que
# dans la branche non-resume de _analyze_book_impl ; suggest_merges (livre
# entier) tourne pourtant aussi en reprise, ré-insérant les mêmes paires sans
# jamais retirer les anciennes -- doublons PENDING accumulés à chaque reprise.
section("_analyze_book (resume=True) : suggest_merges ne duplique pas une suggestion PENDING déjà en base")

from app.core.enums import MergeSuggestionStatus  # noqa: E402
from app.models import CharacterMergeSuggestion  # noqa: E402
from app.services.llm.base import MergeSuggestion  # noqa: E402

_engine7 = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine7)

with Session(_engine7) as _s:
    _book7 = Book(title="ResumeMerge7", source_path="/tmp/resumemerge7.epub")
    _s.add(_book7)
    _s.commit()
    _book7_id = _book7.id
    _survivor7 = Character(book_id=_book7_id, name="Percy Weasley", gender=Gender.MALE)
    _merged7 = Character(book_id=_book7_id, name="Percy", gender=Gender.MALE)
    _s.add(_survivor7)
    _s.add(_merged7)
    _s.commit()
    _survivor7_id, _merged7_id = _survivor7.id, _merged7.id
    # Suggestion déjà présente d'un PREMIER passage d'analyse, avant la reprise.
    _s.add(CharacterMergeSuggestion(
        book_id=_book7_id, survivor_character_id=_survivor7_id,
        merged_character_id=_merged7_id, reason="1er passage",
        status=MergeSuggestionStatus.PENDING,
    ))
    _s.commit()


class _MergeRecorder7:
    async def analyze(self, text, known_characters=None, language=None):
        return LLMChapterResult(characters=[], segments=[])

    async def suggest_merges(self, characters):
        names = {c.name for c in characters}
        if {"Percy Weasley", "Percy"} <= names:
            return [MergeSuggestion(
                survivor_name="Percy Weasley", merged_name="Percy", reason="2e passage",
            )]
        return []


_rec7 = _MergeRecorder7()
_orig_get_provider7 = llm_factory.get_llm_provider
llm_factory.get_llm_provider = lambda settings, override=None: _rec7
try:
    # chapter_data=[] : tous les chapitres restants ont déjà des segments (cas
    # réel d'une reprise où seule la fusion de personnages n'avait pas eu lieu).
    asyncio.run(_analyze_book(_book7_id, [], _engine7, resume=True, already_done=1))
finally:
    llm_factory.get_llm_provider = _orig_get_provider7

with Session(_engine7) as _s:
    _suggestions7 = _s.exec(
        select(CharacterMergeSuggestion).where(CharacterMergeSuggestion.book_id == _book7_id)
    ).all()
    check("1 seule suggestion en base après reprise (pas de doublon)",
          len(_suggestions7) == 1,
          f"got {len(_suggestions7)} : {[(s.reason, s.status) for s in _suggestions7]}")
    check("c'est bien la NOUVELLE suggestion (2e passage), l'ancienne a été purgée",
          _suggestions7 and _suggestions7[0].reason == "2e passage",
          f"got {[s.reason for s in _suggestions7]}")

_engine7.dispose()


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
