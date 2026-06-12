"""Phase 2 verification.
Run: .venv/Scripts/python tests/check_phase2.py
"""
import os
import sys
from pathlib import Path

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
assert len(parsed.chapters) >= 2, f"chapters={len(parsed.chapters)}"
ok(f"title={parsed.title!r}  author={parsed.author!r}  chapters={len(parsed.chapters)}")
for ch in parsed.chapters:
    ok(f"  ch{ch.position}: {ch.title!r}  ({len(ch.raw_text)} chars)")


# ── 3. EpubParsingError ────────────────────────────────────────────────────────
section("EpubParsingError on invalid path")
from app.core.exceptions import EpubParsingError  # noqa: E402

try:
    EpubParser().parse("/nonexistent.epub")
    die("EpubParsingError not raised")
except EpubParsingError as exc:
    ok(f"EpubParsingError raised: {exc}")


# ── 4. _process_book_impl + DB round-trip ─────────────────────────────────────
section("Full pipeline -- _process_book_impl + DB round-trip")
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

with Session(test_engine) as session:
    book = Book(title="temp", source_path=epub_path)
    session.add(book)
    session.commit()
    session.refresh(book)
    book_id = book.id

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
section("HTTP routes -- TestClient")

# Patch process_book in books module to run synchronously (bypasses Huey queue)
import app.api.routes.books as books_module  # noqa: E402

books_module.process_book = lambda book_id: _process_book_impl(book_id)

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

    resp = client.delete(f"/books/{bid}")
    assert resp.status_code == 204
    ok(f"DELETE /books/{bid} -> 204")

    resp = client.get(f"/books/{bid}")
    assert resp.status_code == 404
    ok(f"GET /books/{bid} after delete -> 404")


# ── Cleanup ────────────────────────────────────────────────────────────────────
test_engine.dispose()
for leftover in ("scriptvox_test.db", "huey_test.db"):
    if os.path.exists(leftover):
        os.remove(leftover)
ok("Test DBs cleaned up")

print("\nPHASE 2 OK\n")
