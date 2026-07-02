"""check_phase26.py — Phase 26 (Lot B2 + B3, audit 2026-07-02) : override TTS par livre.

Valide :
  - B2 : assign_voices() reçoit le tts_provider EFFECTIF du livre (book.tts_provider
    si défini, sinon le global) au lieu du global inconditionnellement. Avant ce fix,
    un livre overridé vers qwen alors que le global est autre chose ne bénéficiait
    jamais de la priorité aux voix clonées ; inversement un livre overridé loin de
    qwen alors que le global EST qwen se voyait quand même assigner des clones, qui
    échouent ensuite à la synthèse (resolve_voice ne les connaît pas hors qwen).
  - B3 : PATCH /characters/{id} accepte désormais un voice_id de voix clonée (table
    Voice, kind=CLONED), pas seulement le catalogue figé -- l'assignation automatique
    pouvait déjà choisir un clone, mais la correction manuelle le refusait (422).

Run: .venv/Scripts/python tests/check_phase26.py
"""
import os
import sys
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p26.db",
    "HUEY_DB_PATH": "./huey_test_p26.db",
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

from app.config import get_settings  # noqa: E402
from app.core.enums import Gender, VoiceKind  # noqa: E402
from app.models import Book, Character, Voice  # noqa: E402
from app.services.llm.base import CharacterData, LLMChapterResult  # noqa: E402
from app.workers.tasks import _analyze_book_impl  # noqa: E402
ok("_analyze_book_impl, models, enums, LLM dataclasses")

if not FIXTURE_EPUB.exists():
    fail("Fixture EPUB manquante", str(FIXTURE_EPUB))
    print(f"\n{FAIL} impossible de continuer sans fixture")
    sys.exit(1)


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


class _OneMaleCharacterLLM:
    """Renvoie un unique personnage MALE, aucun dialogue -- suffisant pour exercer
    assign_voices sans dépendre du contenu réel de la fixture EPUB."""

    async def analyze(self, text: str, known_characters=None, language=None) -> LLMChapterResult:
        return LLMChapterResult(
            characters=[CharacterData(name="Hero", description=None, gender=Gender.MALE)],
            segments=[],
        )

    async def suggest_merges(self, characters):
        return []


def _run_analysis(engine, book_tts_provider: str | None, global_tts_provider: str) -> str | None:
    """Crée un livre, seed un clone MALE, lance _analyze_book_impl, retourne le
    voice_id assigné au personnage 'Hero'."""
    with Session(engine) as s:
        book = Book(
            title="B2Test", source_path=str(FIXTURE_EPUB), tts_provider=book_tts_provider,
        )
        s.add(book)
        s.commit()
        s.refresh(book)
        book_id = book.id

        s.add(Voice(
            voice_id="patrick-baud", name="Patrick Baud",
            kind=VoiceKind.CLONED, gender=Gender.MALE,
        ))
        s.commit()

    os.environ["TTS_PROVIDER"] = global_tts_provider
    get_settings.cache_clear()
    with (
        patch("app.core.db.get_engine", return_value=engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_OneMaleCharacterLLM()),
    ):
        _analyze_book_impl(book_id)
    get_settings.cache_clear()

    with Session(engine) as s:
        char = s.exec(select(Character).where(Character.book_id == book_id, Character.name == "Hero")).first()
        return char.voice_id if char else None


# ── 2. B2: override='qwen', global='edgetts' -> le clone MALE est assigné ────
section("B2: livre overridé vers qwen (global edgetts) -> priorité au clone MALE")
_e2 = _make_test_engine()
_voice2 = _run_analysis(_e2, book_tts_provider="qwen", global_tts_provider="edgetts")
check("clone 'patrick-baud' assigné (override qwen honoré malgré global edgetts)",
      _voice2 == "patrick-baud", f"got {_voice2!r}")


# ── 3. B2 (inverse): override='edgetts', global='qwen' -> PAS de clone ───────
section("B2: livre overridé vers edgetts (global qwen) -> PAS de clone (catalogue à la place)")
_e3 = _make_test_engine()
_voice3 = _run_analysis(_e3, book_tts_provider="edgetts", global_tts_provider="qwen")
check("voix catalogue assignée, pas le clone (override edgetts honoré malgré global qwen)",
      _voice3 is not None and _voice3 != "patrick-baud", f"got {_voice3!r}")
check("c'est bien une voix catalogue MALE", _voice3 in {"male_0", "male_1", "male_2"},
      f"got {_voice3!r}")


# ── 4. B2 (régression): pas d'override, global='qwen' -> clone toujours utilisé
section("B2 (régression): pas d'override -> retombe sur le provider global (qwen -> clone)")
_e4 = _make_test_engine()
_voice4 = _run_analysis(_e4, book_tts_provider=None, global_tts_provider="qwen")
check("clone assigné (comportement préexistant, aucun override)",
      _voice4 == "patrick-baud", f"got {_voice4!r}")


# ═══════════════════════════════ B3 ═══════════════════════════════════════

# ── 5. PATCH /characters/{id}: accepte un voice_id de voix clonée ────────────
section("B3: PATCH /characters/{id} accepte un voice_id de voix clonée (kind=CLONED)")
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

_e5 = _make_test_engine()
with Session(_e5) as _s:
    _b5 = Book(title="B3Test", source_path=str(FIXTURE_EPUB))
    _s.add(_b5)
    _s.commit()
    _s.refresh(_b5)
    _char5 = Character(book_id=_b5.id, name="Hero", gender=Gender.MALE)
    _s.add(_char5)
    _s.add(Voice(voice_id="patrick-baud", name="Patrick Baud", kind=VoiceKind.CLONED, gender=Gender.MALE))
    _s.commit()
    _s.refresh(_char5)
    _char5_id = _char5.id


def _session5():
    with Session(_e5) as s:
        yield s


app.dependency_overrides[get_session] = _session5
with TestClient(app, raise_server_exceptions=False) as _tc:
    _r5 = _tc.patch(f"/characters/{_char5_id}", json={"voice_id": "patrick-baud"})
    check("200 (clone accepté)", _r5.status_code == 200, f"got {_r5.status_code} ({_r5.text})")
    if _r5.status_code == 200:
        check("voice_id persisté = clone", _r5.json()["voice_id"] == "patrick-baud", f"got {_r5.json()}")

    # ── 6. Régression: catalogue toujours accepté ────────────────────────────
    section("B3 (régression): PATCH /characters/{id} accepte toujours une voix catalogue")
    _r6 = _tc.patch(f"/characters/{_char5_id}", json={"voice_id": "male_1"})
    check("200 (catalogue toujours accepté)", _r6.status_code == 200, f"got {_r6.status_code}")
    check("voice_id persisté = catalogue", _r6.json()["voice_id"] == "male_1", f"got {_r6.json()}")

    # ── 7. Régression: voice_id totalement inconnu toujours refusé ──────────
    section("B3 (régression): PATCH /characters/{id} refuse un voice_id totalement inconnu")
    _r7 = _tc.patch(f"/characters/{_char5_id}", json={"voice_id": "ghost_voice_xyz"})
    check("422 (ni catalogue ni clone existant)", _r7.status_code == 422, f"got {_r7.status_code}")
app.dependency_overrides.clear()


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
os.environ["TTS_PROVIDER"] = "edgetts"
get_settings.cache_clear()
for _leftover in ("scriptvox_test_p26.db", "huey_test_p26.db"):
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
