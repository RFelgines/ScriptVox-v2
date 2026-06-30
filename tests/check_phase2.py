"""Phase 2 verification.
Run: .venv/Scripts/python tests/check_phase2.py
"""
import io
import os
import shutil
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# All env vars must be set before any app import
os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test.db",
    "HUEY_DB_PATH": "./huey_test.db",
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


def _make_wav_bytes(n_frames: int, framerate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ── 1. Test EPUB fixture ───────────────────────────────────────────────────────
section("Create test EPUB fixture")
from ebooklib import epub  # noqa: E402

fixtures = ROOT / "tests" / "fixtures"
fixtures.mkdir(exist_ok=True)
epub_path = str(fixtures / "test.epub")

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
ok(f"Fixture created: {epub_path}")


# ── 2. EpubParser ─────────────────────────────────────────────────────────────
section("EpubParser -- spine order + metadata")
from app.services.epub.parser import EpubParser, ParsedBook  # noqa: E402

parsed = EpubParser().parse(epub_path)
assert isinstance(parsed, ParsedBook)
assert parsed.title == "Alice in Wonderland", f"title={parsed.title!r}"
assert parsed.author == "Lewis Carroll", f"author={parsed.author!r}"
assert parsed.language == "en", f"language={parsed.language!r}"
assert len(parsed.chapters) >= 2, f"chapters={len(parsed.chapters)}"
ok(f"title={parsed.title!r}  author={parsed.author!r}  language={parsed.language!r}  chapters={len(parsed.chapters)}")
for ch in parsed.chapters:
    ok(f"  ch{ch.position}: {ch.title!r}  ({len(ch.raw_text)} chars)")


# ── 2b. Normalisation des sauts de ligne intra-paragraphe ─────────────────────
section("EpubParser -- hard-wrap interne écrasé, 1 paragraphe = 1 ligne")
ws_path = str(fixtures / "test_whitespace.epub")

ws_book = epub.EpubBook()
ws_book.set_title("Whitespace Test")
ws_book.set_language("fr")
ws_chapter = epub.EpubHtml(title="Chapitre", file_name="chap01.xhtml")
# Hard-wrap typique d'un export XHTML (~80 colonnes) : \n en milieu de phrase,
# et une réplique em-dash coupée par ce même hard-wrap (cas réel HP).
ws_chapter.content = (
    "<html><body>"
    "<p>Alice commençait à se sentir très fatiguée\nde rester assise près de sa sœur.</p>"
    "<p>— Sacré\npetit bonhomme, gloussa Mr Dursley en quittant la maison.</p>"
    "<div><p>Premier paragraphe imbriqué.</p><p>Second paragraphe imbriqué.</p></div>"
    "</body></html>"
).encode("utf-8")
ws_book.add_item(ws_chapter)
ws_nav = epub.EpubNav()
ws_book.add_item(ws_nav)
ws_book.spine = ["nav", ws_chapter]
epub.write_epub(ws_path, ws_book)

ws_parsed = EpubParser().parse(ws_path)
ws_chapters = [c for c in ws_parsed.chapters if "Sacr" in c.raw_text]
assert len(ws_chapters) == 1, f"chapitre de test introuvable parmi {len(ws_parsed.chapters)}"
ws_text = ws_chapters[0].raw_text

assert "fatiguée\nde" not in ws_text, "hard-wrap interne non écrasé (paragraphe narration)"
assert "fatiguée de rester" in ws_text, f"paragraphe narration corrompu: {ws_text!r}"
ok("hard-wrap interne d'un paragraphe de narration -> espace simple")

assert "Sacré\npetit" not in ws_text, "hard-wrap interne non écrasé (réplique em-dash)"
expected_dialogue = "—" + " Sacré petit bonhomme, gloussa Mr Dursley"
assert expected_dialogue in ws_text, "réplique em-dash corrompue: " + repr(ws_text)
ok("hard-wrap interne d'une réplique em-dash -> 1 ligne complète (débloque _split_incise)")

lines = ws_text.split("\n")
assert all(line.strip() for line in lines), f"ligne vide résiduelle: {lines!r}"
assert len(lines) == 4, f"attendu 4 paragraphes (4 lignes), obtenu {len(lines)}: {lines!r}"
ok(f"{len(lines)} paragraphes -> {len(lines)} lignes, séparées par un seul \\n (pas de double-comptage div>p)")


# ── 3. EpubParsingError ────────────────────────────────────────────────────────
section("EpubParsingError on invalid path")
from app.core.exceptions import EpubParsingError  # noqa: E402

try:
    EpubParser().parse("/nonexistent.epub")
    die("EpubParsingError not raised")
except EpubParsingError as exc:
    ok(f"EpubParsingError raised: {exc}")


# ── Mock builders — isolate the worker pipeline from live LLM/TTS services ─────
from app.core.enums import Gender, SegmentType  # noqa: E402
from app.services.llm.base import (  # noqa: E402
    CharacterData,
    LLMChapterResult,
    SegmentData,
)


def _make_mock_llm() -> MagicMock:
    result = LLMChapterResult(
        characters=[
            CharacterData(
                name="Alice",
                description="Protagonist",
                gender=Gender.FEMALE,
                voice_tone="soft",
            ),
        ],
        segments=[
            SegmentData(
                position=1,
                text="Once upon a time.",
                segment_type=SegmentType.NARRATION,
                character_name=None,
            ),
            SegmentData(
                position=2,
                text="Hello!",
                segment_type=SegmentType.DIALOGUE,
                character_name="Alice",
            ),
        ],
    )
    m = MagicMock()
    m.analyze = AsyncMock(return_value=result)
    return m


def _make_mock_tts() -> MagicMock:
    m = MagicMock()
    m.synthesise = AsyncMock(return_value=_make_wav_bytes(50))
    return m


# ── 4. _process_book_impl + DB round-trip (mocked LLM/TTS) ────────────────────
section("Full pipeline -- _process_book_impl + DB round-trip (mocked LLM/TTS)")
import app.core.db as db_module  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.db import init_db  # noqa: E402
from app.core.enums import BookStatus  # noqa: E402
from app.models import Book, Chapter  # noqa: E402
from app.workers.tasks import _process_book_impl  # noqa: E402

get_settings.cache_clear()
test_engine = create_engine(
    "sqlite:///./scriptvox_test.db", connect_args={"check_same_thread": False}
)
db_module._engine = test_engine
init_db(test_engine)

# Copy the fixture into a tempdir so the generated .wav lands there (auto-cleaned),
# never inside the tracked tests/fixtures/ directory.
with tempfile.TemporaryDirectory() as _tmp:
    _tmp_epub = str(Path(_tmp) / "test.epub")
    shutil.copy(epub_path, _tmp_epub)

    with Session(test_engine) as session:
        book = Book(title="temp", source_path=_tmp_epub)
        session.add(book)
        session.commit()
        session.refresh(book)
        book_id = book.id

    with (
        patch("app.services.llm.factory.get_llm_provider", return_value=_make_mock_llm()),
        patch("app.services.tts.factory.get_tts_provider", return_value=_make_mock_tts()),
    ):
        _process_book_impl(book_id)

    with Session(test_engine) as session:
        book = session.get(Book, book_id)
        chapters = session.exec(select(Chapter).where(Chapter.book_id == book_id)).all()

    assert book.status == BookStatus.DONE, f"Expected DONE, got {book.status}"
    assert book.title == "Alice in Wonderland", f"title={book.title!r}"
    assert book.author == "Lewis Carroll", f"author={book.author!r}"
    assert len(chapters) >= 2, f"chapters={len(chapters)}"
    ok(f"status={book.status}  title={book.title!r}  chapters={len(chapters)}")


# ── 5. HTTP routes via TestClient ─────────────────────────────────────────────
section("HTTP routes -- TestClient (worker stubbed)")

# In production process_book is a Huey task dispatched to a separate worker
# process, never executed inside the request. Stub it to a no-op so this section
# validates only the HTTP contract; the worker pipeline is covered by section 4.
import app.api.routes.books as books_module  # noqa: E402

books_module.analyze_book = lambda book_id: None

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

with TestClient(app) as client:
    with open(epub_path, "rb") as fh:
        resp = client.post(
            "/books",
            files={"file": ("alice.epub", fh, "application/epub+zip")},
        )
    if resp.status_code != 202:
        die(f"POST /books: expected 202, got {resp.status_code} -- {resp.text}")
    body = resp.json()
    bid = body["id"]
    ok(f"POST /books -> 202  id={bid}  status={body['status']!r}")

    resp = client.get(f"/books/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    ok(f"GET /books/{bid} -> 200  status={data['status']!r}  title={data['title']!r}")

    resp = client.get("/books")
    assert resp.status_code == 200
    ok(f"GET /books -> 200  count={len(resp.json())}")

    # Seed orphan-file fields directly (simulates a book whose book-level WAV/MP3 and
    # data/{id}/ folder — cover + per-chapter WAV — were already generated before
    # deletion; the stubbed analyze_book above never produces these).
    _del_dir = Path("data") / str(bid)
    _del_dir.mkdir(parents=True, exist_ok=True)
    (_del_dir / "cover.jpg").write_bytes(b"fake-cover")
    (_del_dir / "ch1.wav").write_bytes(b"fake-chapter-wav")

    with tempfile.TemporaryDirectory() as _del_tmp:
        _del_audio = Path(_del_tmp) / "book.wav"
        _del_mp3 = Path(_del_tmp) / "book.mp3"
        _del_audio.write_bytes(b"fake-audio")
        _del_mp3.write_bytes(b"fake-mp3")

        with Session(test_engine) as _del_s:
            _del_book = _del_s.get(Book, bid)
            _del_book.audio_path = str(_del_audio)
            _del_book.mp3_path = str(_del_mp3)
            _del_s.add(_del_book)
            _del_s.commit()

        resp = client.delete(f"/books/{bid}")
        assert resp.status_code == 204
        ok(f"DELETE /books/{bid} -> 204")

        resp = client.get(f"/books/{bid}")
        assert resp.status_code == 404
        ok(f"GET /books/{bid} after delete -> 404")

        assert not _del_audio.exists(), f"audio_path not removed: {_del_audio}"
        assert not _del_mp3.exists(), f"mp3_path not removed: {_del_mp3}"
        ok("book audio_path / mp3_path removed from disk")

    assert not _del_dir.exists(), f"data/{bid}/ dir not removed: {_del_dir}"
    ok(f"data/{bid}/ directory (cover + chapter WAV) removed from disk")


# ── Cleanup ────────────────────────────────────────────────────────────────────
test_engine.dispose()
for leftover in ("scriptvox_test.db", "huey_test.db"):
    if os.path.exists(leftover):
        os.remove(leftover)
ok("Test DBs cleaned up")

print("\nPHASE 2 OK\n")
