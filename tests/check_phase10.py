"""check_phase10.py — Phase 9 Étape 1: extraction de la couverture EPUB.

Vérifie que EpubParser extrait la couverture (image + media_type) ou renvoie
None si absente, et que Book/BookResponse exposent cover_path.
Run: .venv/Scripts/python tests/check_phase10.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p10.db",
    "HUEY_DB_PATH": "./huey_test_p10.db",
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
    msg = f"    FAIL  {label}" + (f" — {detail}" if detail else "")
    print(msg)
    _errors.append(msg)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        ok(label)
    else:
        fail(label, detail)


# Faux bytes JPEG (SOI + EOI) — ebooklib ne valide pas le contenu
_FAKE_JPEG = b"\xff\xd8\xff\xd9"


def _make_epub_with_cover(path: str) -> None:
    from ebooklib import epub
    book = epub.EpubBook()
    book.set_title("Livre avec couverture")
    book.set_language("fr")
    book.set_cover("cover.jpg", _FAKE_JPEG)
    c1 = epub.EpubHtml(title="Chapitre 1", file_name="ch01.xhtml")
    c1.content = b"<html><body><p>Bonjour.</p></body></html>"
    book.add_item(c1)
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c1]
    epub.write_epub(path, book)


def _make_epub_without_cover(path: str) -> None:
    from ebooklib import epub
    book = epub.EpubBook()
    book.set_title("Livre sans couverture")
    book.set_language("fr")
    c1 = epub.EpubHtml(title="Chapitre 1", file_name="ch01.xhtml")
    c1.content = b"<html><body><p>Bonjour.</p></body></html>"
    book.add_item(c1)
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c1]
    epub.write_epub(path, book)


# ── 1. ParsedBook — champs cover_image et cover_media_type ───────────────────
section("ParsedBook -- champs cover_image et cover_media_type")
import dataclasses  # noqa: E402
from app.services.epub.parser import ParsedBook  # noqa: E402

fields = {f.name for f in dataclasses.fields(ParsedBook)}
check("cover_image présent dans ParsedBook", "cover_image" in fields)
check("cover_media_type présent dans ParsedBook", "cover_media_type" in fields)
pb = ParsedBook(title="X", author=None, chapters=[])
check("cover_image par défaut = None", pb.cover_image is None)
check("cover_media_type par défaut = None", pb.cover_media_type is None)


# ── 2. Parser extrait la couverture depuis un EPUB qui en a une ───────────────
section("EpubParser -- EPUB avec couverture => cover_image non nul")
from app.services.epub.parser import EpubParser  # noqa: E402

with tempfile.TemporaryDirectory() as tmpdir:
    p = str(Path(tmpdir) / "with_cover.epub")
    _make_epub_with_cover(p)
    parsed = EpubParser().parse(p)
    check("cover_image non nul", parsed.cover_image is not None)
    check("cover_media_type = image/jpeg", parsed.cover_media_type == "image/jpeg")
    if parsed.cover_image is not None:
        check("contenu = fake JPEG", parsed.cover_image == _FAKE_JPEG)


# ── 3. Parser renvoie None quand pas de couverture ────────────────────────────
section("EpubParser -- EPUB sans couverture => cover_image = None")
with tempfile.TemporaryDirectory() as tmpdir:
    p = str(Path(tmpdir) / "no_cover.epub")
    _make_epub_without_cover(p)
    parsed = EpubParser().parse(p)
    check("cover_image = None", parsed.cover_image is None)
    check("cover_media_type = None", parsed.cover_media_type is None)


# ── 4. Book SQLModel — colonne cover_path ─────────────────────────────────────
section("Book SQLModel -- cover_path (Optional[str] = None)")
from app.models.entities import Book  # noqa: E402

b = Book(title="Test", source_path="test.epub")
check("cover_path par défaut = None", b.cover_path is None)
b.cover_path = "data/1/cover.jpg"
check("cover_path assignable", b.cover_path == "data/1/cover.jpg")


# ── 5. BookResponse — champ cover_path ────────────────────────────────────────
section("BookResponse -- cover_path (Optional[str] = None)")
from app.schemas.book import BookResponse  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from app.core.enums import BookStatus  # noqa: E402

r = BookResponse(
    id=1, title="Test", status=BookStatus.PENDING,
    progress=0.0, created_at=datetime.now(timezone.utc),
)
check("cover_path absent => None par defaut", r.cover_path is None)

r2 = BookResponse(
    id=2, title="Test2", status=BookStatus.DONE,
    progress=100.0, created_at=datetime.now(timezone.utc),
    cover_path="data/2/cover.jpg",
)
check("cover_path renseignable", r2.cover_path == "data/2/cover.jpg")


# ── 6. GET /books/{id}/cover -- 200 avec fichier cover ────────────────────────
section("GET /books/{id}/cover -- 200 OK avec cover bytes")
import tempfile as _tf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import StaticPool  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import SQLModel, Session as _Session  # noqa: E402
from unittest.mock import patch  # noqa: E402

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
SQLModel.metadata.create_all(_engine)


def _get_test_session():
    with _Session(_engine) as s:
        yield s


with _tf.TemporaryDirectory() as _tmpdir:
    _cover_path = Path(_tmpdir) / "cover.jpg"
    _cover_path.write_bytes(_FAKE_JPEG)

    with _Session(_engine) as _s:
        _book = Book(title="Couverture Test", source_path="x.epub", cover_path=str(_cover_path))
        _s.add(_book)
        _s.commit()
        _s.refresh(_book)
        _book_id = _book.id

    from app.main import app  # noqa: E402
    from app.core.db import get_session as _real_get_session  # noqa: E402

    app.dependency_overrides[_real_get_session] = _get_test_session
    client = TestClient(app)

    resp = client.get(f"/books/{_book_id}/cover")
    check("status 200", resp.status_code == 200, str(resp.status_code))
    check("content-type image/jpeg", "image/jpeg" in resp.headers.get("content-type", ""))
    check("body = fake JPEG", resp.content == _FAKE_JPEG)

    # ── 7. 404 si livre inconnu ────────────────────────────────────────────────
    section("GET /books/{id}/cover -- 404 si livre inconnu")
    resp = client.get("/books/99999/cover")
    check("status 404", resp.status_code == 404, str(resp.status_code))

    # ── 8. 404 si pas de cover_path ───────────────────────────────────────────
    section("GET /books/{id}/cover -- 404 si book sans couverture")
    with _Session(_engine) as _s:
        _book_nc = Book(title="Sans couverture", source_path="y.epub")
        _s.add(_book_nc)
        _s.commit()
        _s.refresh(_book_nc)
        _book_nc_id = _book_nc.id

    resp = client.get(f"/books/{_book_nc_id}/cover")
    check("status 404", resp.status_code == 404, str(resp.status_code))
    check("detail no cover", "cover" in resp.json().get("detail", "").lower())

    # ── 9. POST /books/{id}/cover -- 200, cover_path mis a jour ──────────────
    section("POST /books/{id}/cover -- 200 OK, cover_path mis a jour")
    with _Session(_engine) as _s:
        _book_up = Book(title="Upload Cover", source_path="z.epub")
        _s.add(_book_up)
        _s.commit()
        _s.refresh(_book_up)
        _book_up_id = _book_up.id

    resp = client.post(
        f"/books/{_book_up_id}/cover",
        files={"file": ("cover.jpg", _FAKE_JPEG, "image/jpeg")},
    )
    check("status 200", resp.status_code == 200, str(resp.status_code))
    body = resp.json()
    check("cover_path non nul dans reponse", body.get("cover_path") is not None)
    check("cover_path contient cover.jpg", "cover.jpg" in (body.get("cover_path") or ""))

    # ── 10. POST /books/{id}/cover -- 404 si livre inconnu ────────────────────
    section("POST /books/{id}/cover -- 404 si livre inconnu")
    resp = client.post(
        "/books/99999/cover",
        files={"file": ("cover.jpg", _FAKE_JPEG, "image/jpeg")},
    )
    check("status 404", resp.status_code == 404, str(resp.status_code))

    # ── 11. POST /books/{id}/cover -- 422 si type non supporte ───────────────
    section("POST /books/{id}/cover -- 422 si type non supporte")
    resp = client.post(
        f"/books/{_book_up_id}/cover",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    check("status 422", resp.status_code == 422, str(resp.status_code))
    check("detail mentionne type non supporte", "Unsupported" in resp.json().get("detail", ""))

    app.dependency_overrides.clear()


# ── Résumé ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
