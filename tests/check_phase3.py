"""Phase 3 verification.
Run: .venv/Scripts/python tests/check_phase3.py

Set SCRIPTVOX_LIVE_TEST=1 to also run a live LLM call against the configured provider.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p3.db",
    "HUEY_DB_PATH": "./huey_test_p3.db",
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
section("All LLM modules import cleanly")
from app.services.llm.base import (  # noqa: E402
    BaseLLMProvider, CharacterData, LLMChapterResult, SegmentData,
    _chunk_text, _coerce_enum, _estimate_tokens, _merge_chunk_results, _parse_llm_json,
    GEMINI_MAX_TOKENS, SYSTEM_PROMPT,
)
from app.services.llm.gemini import GeminiProvider  # noqa: E402
from app.services.llm.ollama import OllamaProvider  # noqa: E402
from app.services.llm.factory import get_llm_provider  # noqa: E402
from app.core.exceptions import LLMParsingError  # noqa: E402
ok("base, gemini, ollama, factory, LLMParsingError")


# ── 2. BaseLLMProvider is abstract ────────────────────────────────────────────
section("BaseLLMProvider cannot be instantiated")
try:
    BaseLLMProvider()  # type: ignore[abstract]
    die("Expected TypeError -- BaseLLMProvider should be abstract")
except TypeError:
    ok("TypeError raised as expected")


# ── 3. Factory returns correct types ─────────────────────────────────────────
section("get_llm_provider() returns correct concrete class")
from app.config import get_settings  # noqa: E402
get_settings.cache_clear()
settings = get_settings()
provider = get_llm_provider(settings)
assert isinstance(provider, OllamaProvider), f"Expected OllamaProvider, got {type(provider)}"
ok(f"LLM_PROVIDER=ollama => {type(provider).__name__}")

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = "fake-key-for-type-check"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"
get_settings.cache_clear()
gemini_provider = get_llm_provider(get_settings())
assert isinstance(gemini_provider, GeminiProvider), f"Expected GeminiProvider, got {type(gemini_provider)}"
ok(f"LLM_PROVIDER=gemini => {type(gemini_provider).__name__}")

# Restore to ollama for the rest of the tests
os.environ["LLM_PROVIDER"] = "ollama"
del os.environ["GEMINI_API_KEY"]
del os.environ["GEMINI_MODEL"]
get_settings.cache_clear()


# ── 4. _chunk_text -- token budgeting ─────────────────────────────────────────
section("_chunk_text splits correctly")

short = "Hello world."
assert _chunk_text(short, 100) == [short], "_chunk_text should return [text] when under budget"
ok("short text -> single chunk")

# Build a text that will exceed a tiny budget
para_a = "A " * 50   # 100 chars -> ~25 tokens
para_b = "B " * 50
para_c = "C " * 50
long_text = f"{para_a}\n\n{para_b}\n\n{para_c}"
budget = 30  # force split

chunks = _chunk_text(long_text, budget)
assert len(chunks) > 1, f"Expected >1 chunk, got {len(chunks)}"
# Every chunk must fit within budget (or be a single indivisible unit)
for chunk in chunks:
    assert _estimate_tokens(chunk) <= budget or "\n\n" not in chunk, (
        f"Chunk exceeds budget and is still splittable: {_estimate_tokens(chunk)} > {budget}"
    )
# Concatenating chunks should recover the original paragraphs
reconstructed = " ".join(chunks)
for para in [para_a.strip(), para_b.strip(), para_c.strip()]:
    assert para[:10] in reconstructed, f"Paragraph lost in chunking: {para[:10]!r}"
ok(f"long text ({_estimate_tokens(long_text)} tokens) -> {len(chunks)} chunks at budget={budget}")


# ── 5. _parse_llm_json -- valid + invalid ──────────────────────────────────────
section("_parse_llm_json parses valid JSON and raises LLMParsingError on failure")
import json  # noqa: E402
from app.core.enums import AgeCategory, Gender, SegmentType  # noqa: E402

valid_json = json.dumps({
    "characters": [
        {"name": "Alice", "description": "curious girl", "gender": "FEMALE", "voice_tone": "soft"},
    ],
    "segments": [
        {"position": 1, "text": "Alice walked.", "type": "NARRATION", "character_name": None},
        {"position": 2, "text": "Hello!", "type": "DIALOGUE", "character_name": "Alice"},
    ],
})
result = _parse_llm_json(valid_json)
assert len(result.characters) == 1
assert result.characters[0].name == "Alice"
assert result.characters[0].gender == Gender.FEMALE
assert len(result.segments) == 2
assert result.segments[1].segment_type == SegmentType.DIALOGUE
assert result.segments[1].character_name == "Alice"
ok("valid JSON parsed correctly")

try:
    _parse_llm_json("not json at all {{{")
    die("Expected LLMParsingError on invalid JSON")
except LLMParsingError as exc:
    assert exc.raw_response == "not json at all {{{"
    ok(f"LLMParsingError raised on invalid JSON: {exc}")

# With option-A coercion: unrecognized gender -> UNKNOWN, no crash
coerced = _parse_llm_json(json.dumps({
    "characters": [{"name": "Alice", "gender": "INVALID_GENDER", "description": "test"}],
    "segments": [{"position": 1, "text": "x", "type": "NARRATION", "character_name": None}],
}))
assert coerced.characters[0].gender == Gender.UNKNOWN, (
    f"Expected UNKNOWN fallback, got {coerced.characters[0].gender}"
)
ok("unknown gender 'INVALID_GENDER' -> Gender.UNKNOWN fallback, no crash")


# ── 6. _merge_chunk_results ───────────────────────────────────────────────────
section("_merge_chunk_results deduplicates characters and renumbers segments")
from app.services.llm.base import CharacterData, LLMChapterResult, SegmentData  # noqa: E402

r1 = LLMChapterResult(
    characters=[CharacterData("Alice", None, Gender.FEMALE, None)],
    segments=[SegmentData(1, "text1", SegmentType.NARRATION, None)],
)
r2 = LLMChapterResult(
    characters=[
        CharacterData("Alice", "ignored duplicate", Gender.MALE, None),  # duplicate
        CharacterData("Bob", None, Gender.MALE, None),
    ],
    segments=[SegmentData(1, "text2", SegmentType.DIALOGUE, "Bob")],
)
merged = _merge_chunk_results([r1, r2])
assert len(merged.characters) == 2, f"Expected 2 chars, got {len(merged.characters)}"
assert merged.characters[0].name == "Alice"
assert merged.characters[0].gender == Gender.FEMALE  # first occurrence wins
assert merged.characters[1].name == "Bob"
assert merged.segments[0].position == 1
assert merged.segments[1].position == 2  # renumbered continuously
ok("2 chars deduplicated, 2 segments renumbered")


# ── 7. Full pipeline with mock LLM ────────────────────────────────────────────
section("Full pipeline -- _process_book_impl with FakeProvider")
import app.core.db as db_module  # noqa: E402
import app.workers.tasks as tasks_module  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from app.core.db import init_db  # noqa: E402
from app.core.enums import BookStatus  # noqa: E402
from app.models import Book, Character, Chapter, Segment  # noqa: E402
from app.workers.tasks import _process_book_impl  # noqa: E402

get_settings.cache_clear()
test_engine = create_engine(
    "sqlite:///./scriptvox_test_p3.db", connect_args={"check_same_thread": False}
)
db_module._engine = test_engine
init_db(test_engine)

# Build / reuse EPUB fixture
from ebooklib import epub  # noqa: E402
fixtures = ROOT / "tests" / "fixtures"
fixtures.mkdir(exist_ok=True)
epub_path = str(fixtures / "test.epub")
if not Path(epub_path).exists():
    ebook = epub.EpubBook()
    ebook.set_title("Alice in Wonderland")
    ebook.set_language("en")
    ebook.add_author("Lewis Carroll")
    c1 = epub.EpubHtml(title="Down the Rabbit Hole", file_name="chap01.xhtml")
    c1.content = b"<html><body><h1>Down the Rabbit Hole</h1><p>Alice was beginning to be very tired.</p></body></html>"
    ebook.add_item(c1)
    c2 = epub.EpubHtml(title="The Pool of Tears", file_name="chap02.xhtml")
    c2.content = b"<html><body><h1>The Pool of Tears</h1><p>Curiouser and curiouser!</p></body></html>"
    ebook.add_item(c2)
    nav = epub.EpubNav()
    ebook.add_item(nav)
    ebook.spine = ["nav", c1, c2]
    epub.write_epub(epub_path, ebook)

with Session(test_engine) as session:
    book = Book(title="temp", source_path=epub_path)
    session.add(book)
    session.commit()
    session.refresh(book)
    book_id = book.id

# Inject a fake _analyze_book that creates predictable Characters + Segments
_original_analyze_book = tasks_module._analyze_book


async def _fake_analyze_book(
    book_id: int,
    chapter_data: list,
    engine,
) -> None:
    from sqlalchemy import delete as sa_delete
    from datetime import datetime, timezone

    chapter_ids = [cid for cid, _ in chapter_data]

    with Session(engine) as session:
        if chapter_ids:
            session.execute(sa_delete(Segment).where(Segment.chapter_id.in_(chapter_ids)))
        session.execute(sa_delete(Character).where(Character.book_id == book_id))
        session.commit()

    # One character for the whole book
    with Session(engine) as session:
        char = Character(book_id=book_id, name="Alice", gender=Gender.FEMALE)
        session.add(char)
        session.flush()
        char_id = char.id
        session.commit()

    n = len(chapter_data)
    for i, (chapter_id, raw_text) in enumerate(chapter_data):
        with Session(engine) as session:
            session.add(Segment(
                chapter_id=chapter_id,
                position=1,
                text=raw_text[:80] if raw_text else "segment",
                segment_type=SegmentType.NARRATION,
            ))
            bk = session.get(Book, book_id)
            bk.progress = 10.0 + (i + 1) / n * 90.0
            bk.updated_at = datetime.now(timezone.utc)
            session.add(bk)
            session.commit()


_original_synthesise_book = tasks_module._synthesise_book


async def _fake_synthesise_book(book_id: int, source_path: str, engine) -> str:
    return ""  # no real audio needed for this test


tasks_module._analyze_book = _fake_analyze_book
tasks_module._synthesise_book = _fake_synthesise_book

try:
    _process_book_impl(book_id)
finally:
    tasks_module._analyze_book = _original_analyze_book
    tasks_module._synthesise_book = _original_synthesise_book

from sqlmodel import select  # noqa: E402

with Session(test_engine) as session:
    book = session.get(Book, book_id)
    chapters = session.exec(select(Chapter).where(Chapter.book_id == book_id)).all()
    chars = session.exec(select(Character).where(Character.book_id == book_id)).all()
    segs = session.exec(
        select(Segment)
        .join(Chapter, Segment.chapter_id == Chapter.id)
        .where(Chapter.book_id == book_id)
    ).all()

assert book.status == BookStatus.DONE, f"Expected DONE, got {book.status}"
assert book.progress == 100.0, f"Expected 100.0, got {book.progress}"
assert len(chapters) >= 2, f"Expected ≥2 chapters, got {len(chapters)}"
assert len(chars) >= 1, f"Expected ≥1 character, got {len(chars)}"
assert len(segs) >= 1, f"Expected ≥1 segment, got {len(segs)}"
ok(f"status=DONE  chapters={len(chapters)}  characters={len(chars)}  segments={len(segs)}")


# ── 9. _coerce_enum — tolérance aux écarts LLM ───────────────────────────────
section("_coerce_enum normalise casse, ponctuation et alias LLM")

# SegmentType : alias "DIALOG" -> DIALOGUE (quirk réel de qwen3:8b)
assert _coerce_enum("DIALOG, ", SegmentType, SegmentType.NARRATION) == SegmentType.DIALOGUE
ok("'DIALOG, ' (quirk qwen3) -> DIALOGUE")
assert _coerce_enum("dialogue", SegmentType, SegmentType.NARRATION) == SegmentType.DIALOGUE
ok("'dialogue' (minuscules) -> DIALOGUE")
assert _coerce_enum("DIALOG", SegmentType, SegmentType.NARRATION) == SegmentType.DIALOGUE
ok("'DIALOG' (abréviation) -> DIALOGUE")
assert _coerce_enum("NARRATION", SegmentType, SegmentType.NARRATION) == SegmentType.NARRATION
ok("'NARRATION' (correspondance directe) -> NARRATION")

# Gender : casse mixte
assert _coerce_enum("Male", Gender, Gender.UNKNOWN) == Gender.MALE
ok("'Male' (casse mixte) -> MALE")
assert _coerce_enum("female", Gender, Gender.UNKNOWN) == Gender.FEMALE
ok("'female' (minuscules) -> FEMALE")

# Valeur totalement inconnue -> défaut, sans crash
assert _coerce_enum("COMPLETELY_BIZARRE", SegmentType, SegmentType.NARRATION) == SegmentType.NARRATION
ok("valeur inconnue -> défaut NARRATION, pas de crash")

# _parse_llm_json end-to-end avec le vrai quirk de qwen3
bad_json = json.dumps({
    "characters": [{"name": "Harry", "description": "wizard", "gender": "MALE", "voice_tone": "brave"}],
    "segments": [
        {"position": 1, "text": "Harry said something.", "type": "DIALOG, ", "character_name": "Harry"},
        {"position": 2, "text": "Narrator text.", "type": "NARRATION", "character_name": None},
    ],
})
r = _parse_llm_json(bad_json)
assert r.segments[0].segment_type == SegmentType.DIALOGUE, (
    f"Expected DIALOGUE, got {r.segments[0].segment_type}"
)
ok("_parse_llm_json: 'DIALOG, ' dans le JSON -> SegmentType.DIALOGUE")
assert r.segments[1].segment_type == SegmentType.NARRATION
ok("_parse_llm_json: 'NARRATION' dans le JSON -> SegmentType.NARRATION (pas de régression)")


# ── 8. Live LLM (optional, gated by SCRIPTVOX_LIVE_TEST=1) ───────────────────
if os.environ.get("SCRIPTVOX_LIVE_TEST") == "1":
    section("Live LLM call (SCRIPTVOX_LIVE_TEST=1)")
    import asyncio  # noqa: E402
    get_settings.cache_clear()
    live_settings = get_settings()
    live_provider = get_llm_provider(live_settings)
    sample = "Alice sat by the river. \"I'm bored,\" she said to her sister."
    live_result = asyncio.run(live_provider.analyze(sample))
    assert len(live_result.segments) >= 1, "Expected at least 1 segment from live call"
    ok(f"live call OK  characters={len(live_result.characters)}  segments={len(live_result.segments)}")
    for seg in live_result.segments:
        ok(f"  [{seg.segment_type.value}] {seg.text[:60]!r}")
else:
    section("Live LLM call (skipped -- set SCRIPTVOX_LIVE_TEST=1 to enable)")
    ok("skipped")


# ── Cleanup ───────────────────────────────────────────────────────────────────
test_engine.dispose()
for leftover in ("scriptvox_test_p3.db", "huey_test_p3.db"):
    if os.path.exists(leftover):
        os.remove(leftover)
ok("Test DBs cleaned up")

print("\nPHASE 3 OK\n")
