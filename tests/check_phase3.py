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
    _segment_text, _Span,
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


# ── 3b. Network failure -> LLMRequestError, NOT LLMParsingError ──────────────
section("Provider analyze()/suggest_merges(): échec réseau -> LLMRequestError ; JSON invalide -> toujours LLMParsingError")
import asyncio  # noqa: E402
from app.core.exceptions import LLMRequestError  # noqa: E402
from app.core.enums import Gender as _Gender  # noqa: E402
from app.services.llm.base import CharacterData as _CharacterData  # noqa: E402

_two_chars = [
    _CharacterData(name="Alice", description="d", gender=_Gender.FEMALE),
    _CharacterData(name="Bob", description="d", gender=_Gender.MALE),
]


class _FakeOllamaResponse:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


async def _ollama_network_failure(*_a, **_kw):
    raise ConnectionError("simulated network failure")


async def _ollama_bad_json(*_a, **_kw):
    return _FakeOllamaResponse("not json at all {{{")


provider._client.chat = _ollama_network_failure
try:
    asyncio.run(provider.analyze("some chapter text"))
    die("Expected LLMRequestError on network failure (Ollama analyze)")
except LLMRequestError:
    ok("OllamaProvider.analyze(): échec réseau -> LLMRequestError")

try:
    asyncio.run(provider.suggest_merges(_two_chars))
    die("Expected LLMRequestError on network failure (Ollama suggest_merges)")
except LLMRequestError:
    ok("OllamaProvider.suggest_merges(): échec réseau -> LLMRequestError")

provider._client.chat = _ollama_bad_json
try:
    asyncio.run(provider.analyze("some chapter text"))
    die("Expected LLMParsingError on malformed JSON (Ollama analyze)")
except LLMParsingError:
    ok("OllamaProvider.analyze(): JSON invalide -> toujours LLMParsingError (régression)")


class _FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


async def _gemini_network_failure(*_a, **_kw):
    raise ConnectionError("simulated network failure")


async def _gemini_bad_json(*_a, **_kw):
    return _FakeGeminiResponse("not json at all {{{")


os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = "fake-key-for-type-check"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"
get_settings.cache_clear()
_gemini_provider_2 = get_llm_provider(get_settings())
assert isinstance(_gemini_provider_2, GeminiProvider)

_gemini_provider_2._client.aio.models.generate_content = _gemini_network_failure
try:
    asyncio.run(_gemini_provider_2.analyze("some chapter text"))
    die("Expected LLMRequestError on network failure (Gemini analyze)")
except LLMRequestError:
    ok("GeminiProvider.analyze(): échec réseau -> LLMRequestError")

_gemini_provider_2._client.aio.models.generate_content = _gemini_bad_json
try:
    asyncio.run(_gemini_provider_2.analyze("some chapter text"))
    die("Expected LLMParsingError on malformed JSON (Gemini analyze)")
except LLMParsingError:
    ok("GeminiProvider.analyze(): JSON invalide -> toujours LLMParsingError (régression)")

os.environ["LLM_PROVIDER"] = "ollama"
del os.environ["GEMINI_API_KEY"]
del os.environ["GEMINI_MODEL"]
get_settings.cache_clear()


# ── 3c. Dynamic read timeout -- floor + tokens scaling, applied to the httpx client ──
section("OllamaProvider: timeout de lecture dynamique = floor + tokens_estimés/1000 * per_1k_tokens")
from app.services.llm.base import (  # noqa: E402
    _build_user_prompt as _b_build_user_prompt,
    _compute_read_timeout,
    _pre_segment as _b_pre_segment,
)

assert _compute_read_timeout("a" * 4000, floor=600.0, per_1k_tokens=200.0) == 800.0, (
    "1000 tokens estimés (4000 chars) -> floor 600 + 1*200 = 800"
)
assert _compute_read_timeout("", floor=600.0, per_1k_tokens=200.0) == 600.0, (
    "texte vide -> reste exactement au plancher"
)
assert 600.0 < _compute_read_timeout("short", floor=600.0, per_1k_tokens=200.0) < 601.0, (
    "texte minuscule -> proche du plancher (extra quasi nul)"
)
ok("_compute_read_timeout: floor + tokens/1000 * per_1k_tokens")


async def _ollama_capture_timeout(*_a, **_kw):
    return _FakeOllamaResponse('{"characters": [], "attributions": []}')


from app.services.llm.ollama import _NO_THINK_SUFFIX  # noqa: E402

_dyn_chapter_text = "Elle marcha lentement vers la porte. " * 500  # assez gros pour dépasser le plancher
provider._client.chat = _ollama_capture_timeout
asyncio.run(provider.analyze(_dyn_chapter_text))
_dyn_prompt = _b_build_user_prompt(_b_pre_segment(_dyn_chapter_text), None) + _NO_THINK_SUFFIX
_expected_timeout = _compute_read_timeout(
    _dyn_prompt, provider._read_timeout_floor, provider._timeout_per_1k_tokens
)
assert _expected_timeout > provider._read_timeout_floor, "le texte doit dépasser le plancher pour ce test"
assert provider._client._client.timeout.read == _expected_timeout, (
    f"timeout.read={provider._client._client.timeout.read} attendu {_expected_timeout}"
)
ok(f"timeout dynamique appliqué au client httpx interne : {_expected_timeout:.1f}s "
   f"(floor={provider._read_timeout_floor}s)")


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


# ── 5. _parse_llm_json -- format {characters, attributions} + reconstruction ──
section("_parse_llm_json parse {characters, attributions} et reconstruit les segments")
import json  # noqa: E402
from app.core.enums import AgeCategory, Gender, SegmentType  # noqa: E402

_test_spans = [
    _Span(1, "Alice walked.", False),
    _Span(2, '"Hello!"', True),
]
valid_json = json.dumps({
    "characters": [
        {"name": "Alice", "description": "curious girl", "gender": "FEMALE", "voice_tone": "soft"},
    ],
    "attributions": [{"index": 2, "character_name": "Alice"}],
})
result = _parse_llm_json(valid_json, _test_spans)
assert len(result.characters) == 1
assert result.characters[0].name == "Alice"
assert result.characters[0].gender == Gender.FEMALE
assert len(result.segments) == 2
assert result.segments[0].segment_type == SegmentType.NARRATION
assert result.segments[0].character_name is None
assert result.segments[1].segment_type == SegmentType.DIALOGUE
assert result.segments[1].character_name == "Alice"
assert result.segments[1].text == "Hello!", f"délimiteurs non retirés: {result.segments[1].text!r}"
ok("JSON valide parsé, segments reconstruits, délimiteurs retirés")

# Émotion par réplique (Phase 14 B1) : présente sur le dialogue, absente sur la narration
emo_json = json.dumps({
    "characters": [
        {"name": "Alice", "description": "curious girl", "gender": "FEMALE", "voice_tone": "soft"},
    ],
    "attributions": [{"index": 2, "character_name": "Alice", "emotion": "furious and panicked"}],
})
emo_result = _parse_llm_json(emo_json, _test_spans)
assert emo_result.segments[1].emotion == "furious and panicked", (
    f"emotion non extraite: {emo_result.segments[1].emotion!r}"
)
assert emo_result.segments[0].emotion is None, (
    f"narration ne doit jamais porter d'emotion: {emo_result.segments[0].emotion!r}"
)
ok("emotion extraite sur le dialogue, absente sur la narration")

# Rétrocompat : JSON sans champ emotion -> None, pas de crash
no_emo = _parse_llm_json(valid_json, _test_spans)
assert no_emo.segments[1].emotion is None, f"attendu None, got {no_emo.segments[1].emotion!r}"
ok("JSON sans 'emotion' (ancien format) -> emotion=None, pas de crash")

try:
    _parse_llm_json("not json at all {{{", [])
    die("Expected LLMParsingError on invalid JSON")
except LLMParsingError as exc:
    assert exc.raw_response == "not json at all {{{"
    ok(f"LLMParsingError sur JSON invalide : {exc}")

# Entrée d'attribution malformée (chaîne au lieu d'objet) -> ignorée, pas de crash
# (trouvé sur un vrai run HP : un chapitre dense a perdu 26 min de calcul LLM sur ce cas)
_malformed_attr_json = json.dumps({
    "characters": [
        {"name": "Alice", "description": "curious girl", "gender": "FEMALE"},
    ],
    "attributions": ["oops, just a string", {"index": 2, "character_name": "Alice"}],
})
_malformed_attr_result = _parse_llm_json(_malformed_attr_json, _test_spans)
assert _malformed_attr_result.segments[1].character_name == "Alice", (
    "l'entrée valide doit quand même être traitée malgré l'entrée malformée"
)
ok("attribution malformée (chaîne au lieu d'objet) -> ignorée, entrée valide suivante traitée")

# Entrée de personnage malformée (chaîne au lieu d'objet) -> ignorée, pas de crash
_malformed_char_json = json.dumps({
    "characters": ["oops, just a string", {"name": "Bob", "gender": "MALE"}],
    "attributions": [],
})
_malformed_char_result = _parse_llm_json(_malformed_char_json, _test_spans)
assert len(_malformed_char_result.characters) == 1
assert _malformed_char_result.characters[0].name == "Bob"
ok("personnage malformé (chaîne au lieu d'objet) -> ignoré, personnage valide suivant traité")

# Gender inconnu -> UNKNOWN, pas de crash
coerced = _parse_llm_json(json.dumps({
    "characters": [{"name": "Alice", "gender": "INVALID_GENDER", "description": "test"}],
    "attributions": [],
}), [_Span(1, "x", False)])
assert coerced.characters[0].gender == Gender.UNKNOWN, (
    f"Expected UNKNOWN fallback, got {coerced.characters[0].gender}"
)
ok("gender inconnu 'INVALID_GENDER' -> Gender.UNKNOWN, pas de crash")

# Attribution vers personnage inconnu -> character_name=None (fallback gracieux)
fallback = _parse_llm_json(json.dumps({
    "characters": [{"name": "Alice", "gender": "FEMALE", "description": "test"}],
    "attributions": [{"index": 2, "character_name": "PERSONNAGE_INCONNU"}],
}), _test_spans)
assert fallback.segments[1].character_name is None, (
    f"Expected None fallback, got {fallback.segments[1].character_name!r}"
)
ok("attribution personnage inconnu -> character_name=None, pas de crash")

# Audit 2026-07-02 (F2/m3) : index d'attribution en string -> coercé en int, matché
# quand même (avant le fix : silencieusement perdu, span.index int ne matchait jamais)
_str_index_result = _parse_llm_json(json.dumps({
    "characters": [{"name": "Alice", "gender": "FEMALE"}],
    "attributions": [{"index": "2", "character_name": "Alice"}],
}), _test_spans)
assert _str_index_result.segments[1].character_name == "Alice", (
    f"index string '2' doit être coercé en int et matcher span.index=2, "
    f"got {_str_index_result.segments[1].character_name!r}"
)
ok("attribution avec index string '2' -> coercé en int, attribution appliquée")

# index non convertible -> attribution ignorée (pas de crash, pas de faux match)
_bad_index_result = _parse_llm_json(json.dumps({
    "characters": [{"name": "Alice", "gender": "FEMALE"}],
    "attributions": [{"index": "not_a_number", "character_name": "Alice"}],
}), _test_spans)
assert _bad_index_result.segments[1].character_name is None, (
    f"index non convertible doit être ignoré, got {_bad_index_result.segments[1].character_name!r}"
)
ok("attribution avec index non convertible -> ignorée, pas de crash")

# Audit 2026-07-02 (F2/m3) : personnage sans 'name' -> ignoré + WARNING, PAS de
# LLMParsingError qui ferait échouer tout le chapitre (avant le fix : KeyError
# levé pendant la compréhension de liste, attrapé par le except global du dessous)
_no_name_result = _parse_llm_json(json.dumps({
    "characters": [
        {"gender": "MALE", "description": "sans nom"},
        {"name": "Bob", "gender": "MALE"},
    ],
    "attributions": [],
}), [_Span(1, "x", False)])
assert len(_no_name_result.characters) == 1, (
    f"le personnage sans 'name' doit être ignoré, pas planter tout le parsing, "
    f"got {_no_name_result.characters}"
)
assert _no_name_result.characters[0].name == "Bob"
ok("personnage sans 'name' -> ignoré (WARNING), personnage valide suivant traité, pas de crash")


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

# Emotion (Phase 14 B1) doit survivre à la reconstruction inter-chunks (régression silencieuse
# si _merge_chunk_results oublie de la propager -- un chapitre découpé en plusieurs chunks
# par _chunk_text perdrait alors l'emotion sans erreur visible).
r3 = LLMChapterResult(
    characters=[],
    segments=[SegmentData(1, "text3", SegmentType.DIALOGUE, "Bob", emotion="cheerful")],
)
merged2 = _merge_chunk_results([r1, r3])
assert merged2.segments[1].emotion == "cheerful", (
    f"emotion perdue par _merge_chunk_results: {merged2.segments[1].emotion!r}"
)
ok("emotion propagée à travers _merge_chunk_results (renumbering inter-chunks)")


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
    resume: bool = False,
    already_done: int = 0,
) -> bool:
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

    return True


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


# ── _pre_segment — découpage déterministe narration/dialogue (§2.7, B-2a) ─────
section("_pre_segment détecte les délimiteurs FR/EN sans perdre un mot")
from app.services.llm.base import _Span, _build_user_prompt, _pre_segment  # noqa: E402,F401

# Guillemets droits (EN)
sample_en = 'Alice sat. "Hello," she said.'
spans_en = _pre_segment(sample_en)
dialogue_en = [s for s in spans_en if s.is_dialogue]
assert len(dialogue_en) == 1, f"Expected 1 dialogue span, got {len(dialogue_en)}"
assert "Hello" in dialogue_en[0].text
assert "".join(s.text for s in spans_en) == sample_en, "invariant byte-exact violé (EN)"
ok('guillemets droits: "Hello," -> 1 dialogue, narration autour, byte-exact')

# Guillemets français « »
sample_fr = "Il arriva. « Bonjour », dit-il."
spans_fr = _pre_segment(sample_fr)
dialogue_fr = [s for s in spans_fr if s.is_dialogue]
assert len(dialogue_fr) == 1 and "Bonjour" in dialogue_fr[0].text
assert "".join(s.text for s in spans_fr) == sample_fr, "invariant byte-exact violé (FR «»)"
ok("guillemets « » -> 1 dialogue, byte-exact")

# Tiret cadratin SANS incise -> reste 1 seul span dialogue
sample_dash = "Elle réfléchit.\n— Tu viens avec nous demain ?"
spans_dash = _pre_segment(sample_dash)
dialogue_dash = [s for s in spans_dash if s.is_dialogue]
assert len(dialogue_dash) == 1, f"Expected 1 dash-dialogue span, got {len(dialogue_dash)}"
assert dialogue_dash[0].text.lstrip().startswith("—")
assert "".join(s.text for s in spans_dash) == sample_dash, "invariant byte-exact violé (tiret)"
ok("ligne ouverte par — sans incise -> 1 dialogue, byte-exact")

# Narration pure : un seul span, jamais dialogue
sample_narr = "Le soleil se couchait sur la ville endormie."
spans_narr = _pre_segment(sample_narr)
assert len(spans_narr) == 1 and spans_narr[0].is_dialogue is False
assert spans_narr[0].text == sample_narr
ok("narration pure -> 1 span narration")

# Index 1-based et contigus + zéro mot perdu sur échantillon mixte
sample_mix = 'Le matin. « Salut ! » Puis le soir. "Bonsoir." Fin.'
spans_mix = _pre_segment(sample_mix)
assert [s.index for s in spans_mix] == list(range(1, len(spans_mix) + 1)), "indices non contigus"
assert "".join(s.text for s in spans_mix) == sample_mix, "invariant byte-exact violé (mixte)"
assert len([s for s in spans_mix if s.is_dialogue]) == 2
ok(f"indices contigus 1..{len(spans_mix)}, 2 dialogues, zéro mot perdu")


# ── _build_user_prompt — spans numérotés/tagués pour le LLM (§2.7, B-2a) ──────
section("_build_user_prompt formate les spans numérotés/tagués")
prompt = _build_user_prompt(spans_mix)
for s in spans_mix:
    if not " ".join(s.text.split()):
        continue
    tag = "DIALOGUE" if s.is_dialogue else "NARRATION"
    assert f"[{s.index}][{tag}]" in prompt, f"span {s.index} ({tag}) absent du prompt"
ok("chaque span affichable présent avec [index][TYPE]")
assert "[DIALOGUE]" in prompt and "[NARRATION]" in prompt
ok("tags DIALOGUE et NARRATION présents")
assert "\n\n" not in prompt, "le prompt ne doit pas contenir de double saut de ligne"
ok("whitespace normalisé dans le rendu")


# ── _split_incise — l'incise FR part en narration (§2.7) ──────────────────────
section("_pre_segment isole l'incise (« dit-elle ») du dialogue en tiret cadratin")
from app.services.llm.base import _split_incise  # noqa: E402,F401

# Incise par inversion clitique, après virgule
s1 = "— Je ne te crois pas, dit-elle froidement."
sp1 = _pre_segment(s1)
assert "".join(s.text for s in sp1) == s1, "byte-exact violé (incise virgule)"
assert [s.is_dialogue for s in sp1] == [True, False], \
    f"attendu [dialogue, narration], eu {[s.is_dialogue for s in sp1]}"
assert "dit-elle" in sp1[1].text and "dit-elle" not in sp1[0].text
ok("« …pas, dit-elle froidement. » -> dialogue + narration, byte-exact")

# Indices 1-based contigus après split
assert [s.index for s in sp1] == [1, 2], f"indices non contigus après split: {[s.index for s in sp1]}"
ok("indices 1-based contigus après extraction d'incise")

# Incise après point d'interrogation
s2 = "— Tu viens ? demanda-t-elle."
sp2 = _pre_segment(s2)
assert "".join(s.text for s in sp2) == s2, "byte-exact violé (incise ?)"
assert [s.is_dialogue for s in sp2] == [True, False]
assert sp2[0].text.rstrip().endswith("?") and "demanda-t-elle" in sp2[1].text
ok("« Tu viens ? demanda-t-elle. » -> dialogue (?) + narration")

# Incise verbe + nom propre (cas HP : « dit Harry »)
s3 = "— Bonjour, dit Harry."
sp3 = _pre_segment(s3)
assert "".join(s.text for s in sp3) == s3, "byte-exact violé (verbe+nom)"
assert [s.is_dialogue for s in sp3] == [True, False]
assert "Harry" in sp3[1].text
ok("« Bonjour, dit Harry. » -> dialogue + narration (verbe+nom propre)")

# Pas d'incise -> dialogue intact (aucun faux positif, pas de sur-segmentation)
s4 = "— Quelle belle journée !"
sp4 = _pre_segment(s4)
assert [s.is_dialogue for s in sp4] == [True], f"sur-segmentation indue: {[s.is_dialogue for s in sp4]}"
ok("réplique sans incise -> reste 1 dialogue (pas de faux positif)")

# Dialogue REPRIS après incise -> non splitté (borné, jamais de crash ni mot perdu)
s5 = "— Non, répondit-il, mais je viendrai demain."
sp5 = _pre_segment(s5)
assert "".join(s.text for s in sp5) == s5, "byte-exact violé (dialogue repris)"
assert [s.is_dialogue for s in sp5] == [True], \
    f"dialogue repris ne doit PAS être splitté (borné): {[s.is_dialogue for s in sp5]}"
ok("dialogue repris après incise -> non splitté (borné), byte-exact")

# Guillemets : l'incise est déjà hors « » -> comportement inchangé
s6 = "Il arriva. « Bonjour », dit-il."
sp6 = _pre_segment(s6)
assert "".join(s.text for s in sp6) == s6, "byte-exact violé (guillemets inchangé)"
assert len([s for s in sp6 if s.is_dialogue]) == 1
ok("guillemets « » -> incise déjà externe, 1 dialogue (inchangé)")

# Verbe réflexif + apostrophe TYPOGRAPHIQUE (’ U+2019) — celle des vrais EPUB, pas le ' droit
s7 = "— Sacré petit bonhomme, s’exclama Mr Dursley."
sp7 = _pre_segment(s7)
assert "".join(s.text for s in sp7) == s7, "byte-exact violé (apostrophe typographique)"
assert [s.is_dialogue for s in sp7] == [True, False], \
    f"incise à apostrophe typographique non détectée: {[s.is_dialogue for s in sp7]}"
assert "Dursley" in sp7[1].text
ok("« s’exclama » (apostrophe typographique ’) -> dialogue + narration")

# Inversion clitique réflexive + apostrophe TYPOGRAPHIQUE (« s’écria-t-il »)
s8 = "— Attends ! s’écria-t-il."
sp8 = _pre_segment(s8)
assert "".join(s.text for s in sp8) == s8, "byte-exact violé (clitique typographique)"
assert [s.is_dialogue for s in sp8] == [True, False], \
    f"clitique à apostrophe typographique non détecté: {[s.is_dialogue for s in sp8]}"
ok("« s’écria-t-il » (apostrophe typographique ’) -> dialogue + narration")

# _segment_text : dialogue sans — ni virgule orpheline ; incise lue telle quelle
assert _segment_text(sp1[0]) == "Je ne te crois pas", \
    f"dialogue mal nettoyé: {_segment_text(sp1[0])!r}"
assert _segment_text(sp1[1]).startswith("dit-elle"), \
    f"incise narration mal nettoyée: {_segment_text(sp1[1])!r}"
ok("_segment_text: dialogue sans — ni virgule traînante ; incise lue par le narrateur")


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
