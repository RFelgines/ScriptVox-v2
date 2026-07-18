"""Phase 16 Étape 1 — schéma DB pour la fusion de personnages (CharacterMergeSuggestion).
Run: .venv/Scripts/python tests/check_phase16.py
"""
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p16.db",
    "HUEY_DB_PATH": "./huey_test_p16.db",
    "DATA_DIR": "./data_test",
    "PIPER_VOICES_DIR": "./voices",
    "PIPER_BINARY_PATH": sys.executable,
})

_n = 0


def section(title: str) -> None:
    global _n
    _n += 1
    print(f"\n[{_n}] {title}")


def ok(msg: str) -> None:
    print(f"    ok  {msg}")


def die(msg: str) -> None:
    print(f"  FAIL  {msg}")
    sys.exit(1)


# ── 1. Imports ────────────────────────────────────────────────────────────────
section("Phase 16 modules import cleanly")
from sqlmodel import Session, create_engine, select  # noqa: E402

from app.core.db import init_db  # noqa: E402
from app.core.enums import MergeSuggestionStatus  # noqa: E402
from app.models import Book, Character, CharacterMergeSuggestion  # noqa: E402
ok("MergeSuggestionStatus, CharacterMergeSuggestion")


# ── 2. MergeSuggestionStatus enum sanity ─────────────────────────────────────
section("MergeSuggestionStatus — PENDING/ACCEPTED/REJECTED")
assert MergeSuggestionStatus.PENDING.value == "PENDING"
assert MergeSuggestionStatus.ACCEPTED.value == "ACCEPTED"
assert MergeSuggestionStatus.REJECTED.value == "REJECTED"
assert len(MergeSuggestionStatus) == 3, f"Expected 3 values, got {len(MergeSuggestionStatus)}"
ok("3 values OK")


# ── Shared engine ─────────────────────────────────────────────────────────────
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
_engine = create_engine(f"sqlite:///{_tmp.name}", connect_args={"check_same_thread": False})
init_db(_engine)


# ── 3. init_db creates the character_merge_suggestion table ─────────────────
section("init_db — table 'character_merge_suggestion' created")
_conn = sqlite3.connect(_tmp.name)
_tables = {
    r[0] for r in _conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
}
_conn.close()
if "character_merge_suggestion" not in _tables:
    die(f"Table 'character_merge_suggestion' missing. Found: {sorted(_tables)}")
ok(f"Tables: {sorted(t for t in _tables if not t.startswith('sqlite_'))}")


# ── 4. Round-trip: Book + 2 Characters + 1 suggestion, default status PENDING ─
section("CharacterMergeSuggestion — round-trip, default status=PENDING")

with Session(_engine) as s:
    book = Book(title="Test", source_path="/tmp/x.epub")
    s.add(book)
    s.commit()
    s.refresh(book)
    book_id = book.id

    survivor = Character(book_id=book_id, name="Mr Dursley")
    merged = Character(book_id=book_id, name="Vernon Dursley")
    s.add(survivor)
    s.add(merged)
    s.commit()
    s.refresh(survivor)
    s.refresh(merged)
    survivor_id, merged_id = survivor.id, merged.id

    suggestion = CharacterMergeSuggestion(
        book_id=book_id,
        survivor_character_id=survivor_id,
        merged_character_id=merged_id,
        reason="Même personnage, deux noms différents.",
    )
    s.add(suggestion)
    s.commit()
    s.refresh(suggestion)
    suggestion_id = suggestion.id

with Session(_engine) as s:
    loaded = s.get(CharacterMergeSuggestion, suggestion_id)
    assert loaded.book_id == book_id
    assert loaded.survivor_character_id == survivor_id
    assert loaded.merged_character_id == merged_id
    assert loaded.reason == "Même personnage, deux noms différents."
    assert loaded.status == MergeSuggestionStatus.PENDING
ok("round-trip OK, default status=PENDING")


# ── 5. Cascade delete: deleting the Book deletes its merge suggestions ──────
section("Deleting Book cascades to CharacterMergeSuggestion (delete-orphan)")

with Session(_engine) as s:
    b = s.get(Book, book_id)
    s.delete(b)
    s.commit()

with Session(_engine) as s:
    remaining = s.exec(
        select(CharacterMergeSuggestion).where(CharacterMergeSuggestion.book_id == book_id)
    ).all()
    assert remaining == [], f"Expected no orphaned suggestions, got {remaining}"
ok("Book deleted -> CharacterMergeSuggestion rows cascaded away")


_engine.dispose()
os.unlink(_tmp.name)
ok("Temp DB cleaned up")

# ── 6. Étape 2 — imports : contrat LLM suggest_merges ────────────────────────
section("Étape 2 — imports : MergeSuggestion, _build_merge_prompt, _parse_merge_json")
from app.config import get_settings  # noqa: E402
from app.core.enums import AgeCategory, Gender  # noqa: E402
from app.core.exceptions import LLMParsingError  # noqa: E402
from app.services.llm.base import (  # noqa: E402
    CharacterData,
    MergeSuggestion,
    _build_merge_prompt,
    _parse_merge_json,
)
from app.services.llm.factory import get_llm_provider  # noqa: E402
from app.services.llm.gemini import GeminiProvider  # noqa: E402
from app.services.llm.ollama import OllamaProvider  # noqa: E402
ok("MergeSuggestion, _build_merge_prompt, _parse_merge_json, providers")


def _char(name: str, gender=Gender.UNKNOWN, age=AgeCategory.UNKNOWN, description=None) -> CharacterData:
    return CharacterData(name=name, description=description, gender=gender, age_category=age)


# ── 7. _build_merge_prompt ────────────────────────────────────────────────────
section("_build_merge_prompt — formats characters with traits, omits empty traits")

_p7_chars = [
    _char("Mr Dursley", gender=Gender.MALE, age=AgeCategory.ADULT, description="Vernon's formal name"),
    _char("Vernon Dursley"),
]
_p7_prompt = _build_merge_prompt(_p7_chars)
assert "Mr Dursley" in _p7_prompt and "Vernon Dursley" in _p7_prompt
assert "gender: MALE" in _p7_prompt and "age: ADULT" in _p7_prompt
assert "- Vernon Dursley" in _p7_prompt, "Character with no traits should render bare (no empty parens)"
assert "Vernon Dursley ()" not in _p7_prompt
ok("traits rendered; trait-less character has no empty parens")


# ── 8. _parse_merge_json ──────────────────────────────────────────────────────
section("_parse_merge_json — valid merges parsed, invalid entries skipped")

_p8_chars = [_char("Mr Dursley"), _char("Vernon Dursley"), _char("Harry")]

_p8_raw_valid = json.dumps({"merges": [
    {"survivor_name": "Mr Dursley", "merged_name": "Vernon Dursley", "reason": "Same person"},
]})
_p8_result = _parse_merge_json(_p8_raw_valid, _p8_chars)
assert len(_p8_result) == 1
assert _p8_result[0] == MergeSuggestion(
    survivor_name="Mr Dursley", merged_name="Vernon Dursley", reason="Same person"
)
ok("valid merge parsed into MergeSuggestion")

# Unknown name -> skipped (no crash)
_p8_raw_unknown = json.dumps({"merges": [
    {"survivor_name": "Mr Dursley", "merged_name": "Nobody", "reason": "?"},
]})
assert _parse_merge_json(_p8_raw_unknown, _p8_chars) == []
ok("unknown character name -> entry skipped, no crash")

# survivor == merged -> skipped
_p8_raw_self = json.dumps({"merges": [
    {"survivor_name": "Harry", "merged_name": "Harry", "reason": "?"},
]})
assert _parse_merge_json(_p8_raw_self, _p8_chars) == []
ok("survivor_name == merged_name -> entry skipped")

# Missing "merges" key -> empty list, no crash
assert _parse_merge_json(json.dumps({}), _p8_chars) == []
ok("missing 'merges' key -> []")

# Malformed JSON -> LLMParsingError (consistent with _parse_llm_json)
try:
    _parse_merge_json("not json", _p8_chars)
    die("Expected LLMParsingError on malformed JSON")
except LLMParsingError:
    ok("malformed JSON -> LLMParsingError")

# raw=None (audit 2026-07-11) : réponse Gemini bloquée par les filtres de
# sécurité -> response.text vaut None -- json.loads(None) lève un TypeError
# brut si non capturé, cf. le même correctif sur _parse_llm_json (check_phase3).
try:
    _parse_merge_json(None, _p8_chars)
    die("Expected LLMParsingError on raw=None")
except LLMParsingError:
    ok("raw=None (réponse LLM bloquée/vide) -> LLMParsingError")
except TypeError as exc:
    die(f"TypeError brut au lieu de LLMParsingError sur raw=None : {exc}")


# ── 9. OllamaProvider / GeminiProvider expose suggest_merges (fast path) ─────
section("OllamaProvider/GeminiProvider.suggest_merges — fast path, <2 characters -> [] (no network)")

os.environ["LLM_PROVIDER"] = "ollama"
get_settings.cache_clear()
_ollama_provider = get_llm_provider(get_settings())
assert isinstance(_ollama_provider, OllamaProvider)
assert asyncio.run(_ollama_provider.suggest_merges([])) == []
assert asyncio.run(_ollama_provider.suggest_merges([_char("Solo")])) == []
ok("OllamaProvider: 0 or 1 character -> [] without calling the client")

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = "fake-key-for-type-check"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"
get_settings.cache_clear()
_gemini_provider = get_llm_provider(get_settings())
assert isinstance(_gemini_provider, GeminiProvider)
assert asyncio.run(_gemini_provider.suggest_merges([])) == []
assert asyncio.run(_gemini_provider.suggest_merges([_char("Solo")])) == []
ok("GeminiProvider: 0 or 1 character -> [] without calling the client")

# Restore env for any later test in this file
os.environ["LLM_PROVIDER"] = "ollama"
del os.environ["GEMINI_API_KEY"]
del os.environ["GEMINI_MODEL"]
get_settings.cache_clear()


# ── 10-12. Étape 3 — câblage worker (_analyze_book persiste les suggestions) ─
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session as _Session, SQLModel, create_engine, select as _select  # noqa: E402

from app.workers.tasks import _analyze_book_impl  # noqa: E402
from app.models import Book, Character  # noqa: E402
from app.core.enums import BookStatus, SegmentType  # noqa: E402
from app.services.llm.base import LLMChapterResult, SegmentData  # noqa: E402

FIXTURE_EPUB = ROOT / "tests" / "fixtures" / "test.epub"


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_mock_llm(suggest_merges_result=None, suggest_merges_side_effect=None) -> MagicMock:
    result = LLMChapterResult(
        characters=[
            _char("Mr Dursley"),
            _char("Vernon Dursley"),
        ],
        segments=[
            SegmentData(position=1, text="He was tall.", segment_type=SegmentType.NARRATION, character_name=None),
            SegmentData(position=2, text="Hello!", segment_type=SegmentType.DIALOGUE, character_name="Mr Dursley"),
        ],
    )
    m = MagicMock()
    m.analyze = AsyncMock(return_value=result)
    if suggest_merges_side_effect is not None:
        m.suggest_merges = AsyncMock(side_effect=suggest_merges_side_effect)
    else:
        m.suggest_merges = AsyncMock(return_value=suggest_merges_result or [])
    return m


def _seed_pending_book(engine, epub_path: str) -> int:
    with _Session(engine) as s:
        book = Book(title="Pending", source_path=epub_path)
        s.add(book)
        s.commit()
        s.refresh(book)
        return book.id


if not FIXTURE_EPUB.exists():
    die(f"Missing test fixture: {FIXTURE_EPUB}")

# Section 10: happy path — suggestion persisted with correct survivor/merged ids
section("_analyze_book: LLM suggests a merge -> CharacterMergeSuggestion persisted")

_s10_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _s10_tmp:
    _s10_epub = Path(_s10_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _s10_epub)
    _s10_book_id = _seed_pending_book(_s10_engine, str(_s10_epub))

    _s10_llm = _make_mock_llm(suggest_merges_result=[
        MergeSuggestion(survivor_name="Mr Dursley", merged_name="Vernon Dursley", reason="Same person"),
    ])

    with (
        patch("app.core.db.get_engine", return_value=_s10_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_s10_llm),
    ):
        _analyze_book_impl(_s10_book_id)

    with _Session(_s10_engine) as _s:
        _s10_book = _s.get(Book, _s10_book_id)
        if _s10_book.status == BookStatus.FAILED:
            die(f"_analyze_book_impl FAILED unexpectedly: {_s10_book.error_message!r}")
        assert _s10_book.status == BookStatus.ANALYZED, f"Expected ANALYZED, got {_s10_book.status}"

        _s10_chars = {
            c.name: c.id
            for c in _s.exec(_select(Character).where(Character.book_id == _s10_book_id)).all()
        }
        assert set(_s10_chars) == {"Mr Dursley", "Vernon Dursley"}, _s10_chars

        _s10_sugg = _s.exec(
            _select(CharacterMergeSuggestion).where(CharacterMergeSuggestion.book_id == _s10_book_id)
        ).all()
        assert len(_s10_sugg) == 1, f"Expected 1 suggestion, got {len(_s10_sugg)}"
        assert _s10_sugg[0].survivor_character_id == _s10_chars["Mr Dursley"]
        assert _s10_sugg[0].merged_character_id == _s10_chars["Vernon Dursley"]
        assert _s10_sugg[0].reason == "Same person"
        assert _s10_sugg[0].status == MergeSuggestionStatus.PENDING
    ok("ANALYZED, 1 CharacterMergeSuggestion persisted with correct survivor/merged ids")


# Section 11: suggest_merges raises -> non-blocking, book still ANALYZED, 0 suggestions
section("_analyze_book: suggest_merges raises -> non-blocking, book still ANALYZED")

_s11_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _s11_tmp:
    _s11_epub = Path(_s11_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _s11_epub)
    _s11_book_id = _seed_pending_book(_s11_engine, str(_s11_epub))

    _s11_llm = _make_mock_llm(suggest_merges_side_effect=RuntimeError("LLM unavailable"))

    with (
        patch("app.core.db.get_engine", return_value=_s11_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_s11_llm),
    ):
        _analyze_book_impl(_s11_book_id)

    with _Session(_s11_engine) as _s:
        _s11_book = _s.get(Book, _s11_book_id)
        assert _s11_book.status == BookStatus.ANALYZED, (
            f"suggest_merges failure must not block analysis, got {_s11_book.status} "
            f"({_s11_book.error_message!r})"
        )
        _s11_sugg = _s.exec(
            _select(CharacterMergeSuggestion).where(CharacterMergeSuggestion.book_id == _s11_book_id)
        ).all()
        assert _s11_sugg == [], f"Expected 0 suggestions on suggest_merges failure, got {_s11_sugg}"
    ok("ANALYZED despite suggest_merges RuntimeError, 0 suggestions persisted")


# Section 12: <2 characters -> suggest_merges not called at all
section("_analyze_book: <2 characters -> suggest_merges not called")

_s12_engine = _make_test_engine()

with tempfile.TemporaryDirectory() as _s12_tmp:
    _s12_epub = Path(_s12_tmp) / "test.epub"
    shutil.copy(FIXTURE_EPUB, _s12_epub)
    _s12_book_id = _seed_pending_book(_s12_engine, str(_s12_epub))

    _s12_llm = MagicMock()
    _s12_llm.analyze = AsyncMock(return_value=LLMChapterResult(
        characters=[_char("Solo")],
        segments=[SegmentData(position=1, text="Alone.", segment_type=SegmentType.NARRATION, character_name=None)],
    ))
    _s12_llm.suggest_merges = AsyncMock(return_value=[])

    with (
        patch("app.core.db.get_engine", return_value=_s12_engine),
        patch("app.services.llm.factory.get_llm_provider", return_value=_s12_llm),
    ):
        _analyze_book_impl(_s12_book_id)

    _s12_llm.suggest_merges.assert_not_called()
ok("1 character detected -> suggest_merges skipped entirely")


# ── 13-17. Étape 4 — API : GET merge-suggestions + accept/reject ────────────
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.models import Chapter, Segment  # noqa: E402
from app.core.enums import SegmentType as _SegmentType  # noqa: E402

_api_engine = _make_test_engine()


def _api_session():
    with _Session(_api_engine) as s:
        yield s


app.dependency_overrides[get_session] = _api_session


def _seed_book_with_chars(engine, names: list[str]) -> tuple[int, dict[str, int]]:
    with _Session(engine) as s:
        book = Book(title="MergeTest", source_path="/tmp/x.epub", status=BookStatus.ANALYZED)
        s.add(book)
        s.commit()
        s.refresh(book)
        book_id = book.id

        ids: dict[str, int] = {}
        for name in names:
            c = Character(book_id=book_id, name=name)
            s.add(c)
            s.commit()
            s.refresh(c)
            ids[name] = c.id
    return book_id, ids


# Section 13: GET /books/{id}/merge-suggestions — 404 unknown book + only PENDING returned
section("GET /books/{id}/merge-suggestions — 404 unknown book, only PENDING returned")

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r13a = _tc.get("/books/9999/merge-suggestions")
    assert _r13a.status_code == 404, f"Expected 404, got {_r13a.status_code}"
ok("404 for unknown book")

_s13_book_id, _s13_ids = _seed_book_with_chars(_api_engine, ["Mr Dursley", "Vernon Dursley", "Harry"])

with _Session(_api_engine) as _s:
    _s.add(CharacterMergeSuggestion(
        book_id=_s13_book_id,
        survivor_character_id=_s13_ids["Mr Dursley"],
        merged_character_id=_s13_ids["Vernon Dursley"],
        reason="Same person",
    ))
    _s.add(CharacterMergeSuggestion(
        book_id=_s13_book_id,
        survivor_character_id=_s13_ids["Mr Dursley"],
        merged_character_id=_s13_ids["Harry"],
        reason="Already resolved",
        status=MergeSuggestionStatus.ACCEPTED,
    ))
    _s.commit()

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r13b = _tc.get(f"/books/{_s13_book_id}/merge-suggestions")
assert _r13b.status_code == 200, f"Expected 200, got {_r13b.status_code} ({_r13b.text})"
_r13b_data = _r13b.json()
assert len(_r13b_data) == 1, f"Expected only the PENDING suggestion, got {_r13b_data}"
assert _r13b_data[0]["status"] == "PENDING"
ok("only the PENDING suggestion is returned, ACCEPTED one is filtered out")


# Section 14: POST /merge-suggestions/{id}/accept — happy path
section("POST /merge-suggestions/{id}/accept — reassigns segments, deletes merged Character")

_s14_book_id, _s14_ids = _seed_book_with_chars(_api_engine, ["Mr Dursley", "Vernon Dursley"])

with _Session(_api_engine) as _s:
    ch = Chapter(book_id=_s14_book_id, position=1, raw_text="x")
    _s.add(ch)
    _s.commit()
    _s.refresh(ch)
    _s.add(Segment(
        chapter_id=ch.id, position=1, text="Hello!",
        segment_type=_SegmentType.DIALOGUE, character_id=_s14_ids["Vernon Dursley"],
    ))
    _s.commit()
    _s14_chapter_id = ch.id

    _s14_sugg = CharacterMergeSuggestion(
        book_id=_s14_book_id,
        survivor_character_id=_s14_ids["Mr Dursley"],
        merged_character_id=_s14_ids["Vernon Dursley"],
        reason="Same person",
    )
    _s.add(_s14_sugg)
    _s.commit()
    _s.refresh(_s14_sugg)
    _s14_sugg_id = _s14_sugg.id

with TestClient(app) as _tc:
    _r14 = _tc.post(f"/merge-suggestions/{_s14_sugg_id}/accept")
assert _r14.status_code == 200, f"Expected 200, got {_r14.status_code} ({_r14.text})"
assert _r14.json()["status"] == "ACCEPTED"

with _Session(_api_engine) as _s:
    assert _s.get(Character, _s14_ids["Vernon Dursley"]) is None, "Merged character should be deleted"
    assert _s.get(Character, _s14_ids["Mr Dursley"]) is not None, "Survivor must remain"
    _seg = _s.exec(select(Segment).where(Segment.chapter_id == _s14_chapter_id)).first()
    assert _seg.character_id == _s14_ids["Mr Dursley"], (
        f"Segment should be reassigned to survivor, got character_id={_seg.character_id}"
    )
ok("merged Character deleted, survivor kept, segment reassigned to survivor")


# Section 15: 404 unknown id, 409 already resolved
section("POST /merge-suggestions/{id}/accept — 404 unknown id, 409 already resolved")

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r15a = _tc.post("/merge-suggestions/9999/accept")
    assert _r15a.status_code == 404, f"Expected 404, got {_r15a.status_code}"
ok("404 for unknown suggestion id")

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r15b = _tc.post(f"/merge-suggestions/{_s14_sugg_id}/accept")  # already ACCEPTED in section 14
    assert _r15b.status_code == 409, f"Expected 409, got {_r15b.status_code}"
ok("409 for already-resolved suggestion")


# Section 16: POST /merge-suggestions/{id}/reject — marks REJECTED, touches nothing else
section("POST /merge-suggestions/{id}/reject — marks REJECTED, characters untouched")

_s16_book_id, _s16_ids = _seed_book_with_chars(_api_engine, ["A", "B"])

with _Session(_api_engine) as _s:
    _s16_sugg = CharacterMergeSuggestion(
        book_id=_s16_book_id,
        survivor_character_id=_s16_ids["A"],
        merged_character_id=_s16_ids["B"],
    )
    _s.add(_s16_sugg)
    _s.commit()
    _s.refresh(_s16_sugg)
    _s16_sugg_id = _s16_sugg.id

with TestClient(app) as _tc:
    _r16 = _tc.post(f"/merge-suggestions/{_s16_sugg_id}/reject")
assert _r16.status_code == 200, f"Expected 200, got {_r16.status_code} ({_r16.text})"
assert _r16.json()["status"] == "REJECTED"

with _Session(_api_engine) as _s:
    assert _s.get(Character, _s16_ids["A"]) is not None
    assert _s.get(Character, _s16_ids["B"]) is not None, "reject must NOT delete the merged character"
ok("REJECTED, both characters untouched")


# Section 17: accepting one suggestion auto-rejects stale siblings (group of 3+)
section("POST /merge-suggestions/{id}/accept — stale sibling suggestions auto-rejected")

_s17_book_id, _s17_ids = _seed_book_with_chars(_api_engine, ["Mr Dursley", "Vernon Dursley", "V. Dursley"])

with _Session(_api_engine) as _s:
    _s17_main = CharacterMergeSuggestion(
        book_id=_s17_book_id,
        survivor_character_id=_s17_ids["Mr Dursley"],
        merged_character_id=_s17_ids["Vernon Dursley"],
    )
    _s17_sibling = CharacterMergeSuggestion(
        book_id=_s17_book_id,
        survivor_character_id=_s17_ids["Vernon Dursley"],  # references the soon-to-be-deleted character
        merged_character_id=_s17_ids["V. Dursley"],
    )
    _s.add(_s17_main)
    _s.add(_s17_sibling)
    _s.commit()
    _s.refresh(_s17_main)
    _s.refresh(_s17_sibling)
    _s17_main_id, _s17_sibling_id = _s17_main.id, _s17_sibling.id

with TestClient(app) as _tc:
    _r17 = _tc.post(f"/merge-suggestions/{_s17_main_id}/accept")
assert _r17.status_code == 200, f"Expected 200, got {_r17.status_code} ({_r17.text})"

with _Session(_api_engine) as _s:
    _sibling_after = _s.get(CharacterMergeSuggestion, _s17_sibling_id)
    assert _sibling_after.status == MergeSuggestionStatus.REJECTED, (
        f"Sibling referencing the deleted character should be auto-rejected, "
        f"got {_sibling_after.status}"
    )
ok("sibling suggestion referencing the now-deleted character auto-rejected")

app.dependency_overrides.clear()


print("\nPHASE 16 (merge suggestions — Étape 1 à 4 : schéma + LLM + worker + API) OK\n")
