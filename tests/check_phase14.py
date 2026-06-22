"""check_phase14.py — Phase 14 Étape A : persistance des personnages entre chapitres.

Le LLM reçoit désormais, à partir du 2e chapitre, la liste des noms de personnages déjà
détectés (BaseLLMProvider.analyze(text, known_characters=None)), pour réutiliser le nom
exact d'un personnage récurrent plutôt que d'en inventer une variante.

Run: .venv/Scripts/python tests/check_phase14.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p14.db",
    "HUEY_DB_PATH": "./huey_test_p14.db",
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


# ── 1. analyze() accepte known_characters (signature) ────────────────────────
section("BaseLLMProvider.analyze accepte known_characters: list[str] | None = None")
import inspect  # noqa: E402
from app.services.llm.base import BaseLLMProvider, SYSTEM_PROMPT, _build_user_prompt, _Span  # noqa: E402

sig = inspect.signature(BaseLLMProvider.analyze)
check("paramètre 'known_characters' présent", "known_characters" in sig.parameters,
      f"params={list(sig.parameters)}")
check("défaut == None", sig.parameters["known_characters"].default is None,
      f"got {sig.parameters['known_characters'].default!r}")


# ── 2. _build_user_prompt -- known_characters absent/vide -> rendu inchangé ──
section("_build_user_prompt: known_characters=None/[] -> rendu identique (no-op)")

_spans = [_Span(1, "Bonjour.", False), _Span(2, "— Ça va ?", True)]
baseline = _build_user_prompt(_spans)
same_none = _build_user_prompt(_spans, None)
same_empty = _build_user_prompt(_spans, [])
check("known_characters=None -> identique à l'appel sans argument", same_none == baseline,
      f"{same_none!r} != {baseline!r}")
check("known_characters=[] -> identique à l'appel sans argument", same_empty == baseline,
      f"{same_empty!r} != {baseline!r}")
check("toujours pas de double saut de ligne (régression check_phase3)", "\n\n" not in baseline)


# ── 3. _build_user_prompt -- known_characters rempli -> préambule injecté ────
section("_build_user_prompt: known_characters=['Mr Dursley', ...] -> préambule présent")

with_known = _build_user_prompt(_spans, ["Mr Dursley", "Mrs Dursley"])
check("contient 'Mr Dursley'", "Mr Dursley" in with_known)
check("contient 'Mrs Dursley'", "Mrs Dursley" in with_known)
check("les spans restent présents après le préambule",
      "[1][NARRATION]" in with_known and "[2][DIALOGUE]" in with_known)
check("préambule avant les spans (ordre)",
      with_known.index("Dursley") < with_known.index("[1]"))


# ── 4. SYSTEM_PROMPT -- règle de réutilisation de nom ────────────────────────
section("SYSTEM_PROMPT mentionne la règle de réutilisation de nom de personnage connu")

check("mentionne la réutilisation exacte du nom",
      "exact" in SYSTEM_PROMPT.lower() and "name" in SYSTEM_PROMPT.lower())
check("mentionne 'known character' (ou équivalent)",
      "known character" in SYSTEM_PROMPT.lower())


# ── 5. Pipeline réel _analyze_book -- known_characters accumulé entre chapitres
section("_analyze_book (réel) -- transmet char_map accumulé au chapitre suivant")

import asyncio  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.enums import Gender, SegmentType  # noqa: E402
from app.models import Book, Character  # noqa: E402
from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData  # noqa: E402
import app.services.llm.factory as llm_factory  # noqa: E402
from app.workers.tasks import _analyze_book  # noqa: E402

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine)

with Session(_engine) as _session:
    _book = Book(title="Test", source_path="/tmp/t.epub")
    _session.add(_book)
    _session.commit()
    _book_id = _book.id


class _RecordingProvider:
    """Renvoie 'Mr Dursley' à chaque chapitre (simule le LLM qui réutilise le nom) et
    enregistre la valeur de known_characters reçue à chaque appel."""

    def __init__(self) -> None:
        self.calls: list[list[str] | None] = []

    async def analyze(self, text: str, known_characters: list[str] | None = None) -> LLMChapterResult:
        self.calls.append(known_characters)
        return LLMChapterResult(
            characters=[CharacterData(name="Mr Dursley", description=None, gender=Gender.MALE)],
            segments=[SegmentData(
                position=1, text=text or "x",
                segment_type=SegmentType.NARRATION, character_name=None,
            )],
        )


_recorder = _RecordingProvider()
_original_get_provider = llm_factory.get_llm_provider
llm_factory.get_llm_provider = lambda settings: _recorder

_chapter_data = [(1, "Chapitre un."), (2, "Chapitre deux.")]

try:
    asyncio.run(_analyze_book(_book_id, _chapter_data, _engine))
finally:
    llm_factory.get_llm_provider = _original_get_provider

check("2 appels enregistrés (1 par chapitre)", len(_recorder.calls) == 2,
      f"got {len(_recorder.calls)}")
check("chapitre 1 -> known_characters vide (aucun personnage connu encore)",
      _recorder.calls[0] == [], f"got {_recorder.calls[0]!r}")
check("chapitre 2 -> known_characters == ['Mr Dursley'] (accumulé du ch.1)",
      _recorder.calls[1] == ["Mr Dursley"], f"got {_recorder.calls[1]!r}")

with Session(_engine) as _session:
    _chars = _session.exec(select(Character).where(Character.book_id == _book_id)).all()
check("1 seul Character créé malgré 2 chapitres (dedup par nom exact toujours actif)",
      len(_chars) == 1, f"got {[c.name for c in _chars]}")

_engine.dispose()


# ── 6. Étape B1 -- Segment.emotion persisté depuis SegmentData.emotion ────────
section("_analyze_book (réel) -- Segment.emotion persisté (dialogue) / None (narration)")

_engine_b1 = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine_b1)

with Session(_engine_b1) as _session_b1:
    _book_b1 = Book(title="Test B1", source_path="/tmp/t.epub")
    _session_b1.add(_book_b1)
    _session_b1.commit()
    _book_b1_id = _book_b1.id


class _EmotionProvider:
    """Renvoie 1 narration (sans emotion) + 1 dialogue (avec emotion)."""

    async def analyze(self, text: str, known_characters: list[str] | None = None) -> LLMChapterResult:
        return LLMChapterResult(
            characters=[CharacterData(name="Bob", description=None, gender=Gender.MALE)],
            segments=[
                SegmentData(
                    position=1, text="La pluie tombait.",
                    segment_type=SegmentType.NARRATION, character_name=None,
                ),
                SegmentData(
                    position=2, text="Sors d'ici !",
                    segment_type=SegmentType.DIALOGUE, character_name="Bob",
                    emotion="furious",
                ),
            ],
        )


llm_factory.get_llm_provider = lambda settings: _EmotionProvider()
try:
    asyncio.run(_analyze_book(_book_b1_id, [(1, "Chapitre.")], _engine_b1))
finally:
    llm_factory.get_llm_provider = _original_get_provider

from app.models import Segment  # noqa: E402

with Session(_engine_b1) as _session_b1:
    _segs = _session_b1.exec(
        select(Segment).where(Segment.chapter_id == 1).order_by(Segment.position)
    ).all()

check("2 segments créés", len(_segs) == 2, f"got {len(_segs)}")
check("narration -> emotion=None en base", _segs[0].emotion is None,
      f"got {_segs[0].emotion!r}")
check("dialogue -> emotion='furious' en base", _segs[1].emotion == "furious",
      f"got {_segs[1].emotion!r}")

_engine_b1.dispose()


# ── Cleanup ───────────────────────────────────────────────────────────────────
for leftover in ("scriptvox_test_p14.db", "huey_test_p14.db"):
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
