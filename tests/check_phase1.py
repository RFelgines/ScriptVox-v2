"""Phase 1 verification — stdlib + installed deps only.
Run: python tests/check_phase1.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_section = 0


def section(title: str) -> None:
    global _section
    _section += 1
    print(f"\n[{_section}] {title}")


def ok(msg: str) -> None:
    print(f"    ok  {msg}")


def die(msg: str) -> None:
    print(f"  FAIL  {msg}")
    sys.exit(1)


_OLLAMA_VARS = {
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "OLLAMA_CONNECT_TIMEOUT": "60",
    "OLLAMA_READ_TIMEOUT": "600",
    "DATABASE_URL": "sqlite:///./scriptvox.db",
    "HUEY_DB_PATH": "./huey.db",
    "DATA_DIR": "./data_test",
    "PIPER_VOICES_DIR": "./voices",
    "PIPER_BINARY_PATH": sys.executable,  # real file, satisfies is_file() check in tests
}


def _set_env(**overrides: str) -> None:
    os.environ.update({**_OLLAMA_VARS, **overrides})


def _del_env(*keys: str) -> None:
    for k in keys:
        os.environ.pop(k, None)


# ─── 1. Config — nominal ──────────────────────────────────────────────────────
section("Config — nominal (ollama)")
# OLLAMA_CHUNK_TOKENS explicitement passé pour éviter que load_dotenv() ne charge
# la valeur du .env (qui peut diverger du défaut code lors du développement).
_set_env(OLLAMA_CHUNK_TOKENS="4000")

from app.config import Settings, get_settings  # noqa: E402

get_settings.cache_clear()
s = get_settings()
assert s.llm_provider == "ollama"
assert s.tts_provider == "piper"
assert s.ollama_connect_timeout == 60.0
assert s.ollama_read_timeout == 600.0
assert s.ollama_chunk_tokens == 4000, "défaut OLLAMA_CHUNK_TOKENS attendu = 4000"
ok(f"LLM={s.llm_provider}  TTS={s.tts_provider}  context={s.ollama_context_tokens} tokens")
ok(f"timeouts: connect={s.ollama_connect_timeout}s  read={s.ollama_read_timeout}s")
ok(f"chunk budget (défaut) = {s.ollama_chunk_tokens} tokens")

# OLLAMA_CHUNK_TOKENS surchargeable par l'environnement
_set_env(OLLAMA_CHUNK_TOKENS="6000")
get_settings.cache_clear()
assert get_settings().ollama_chunk_tokens == 6000, "OLLAMA_CHUNK_TOKENS doit être lu depuis l'env"
_del_env("OLLAMA_CHUNK_TOKENS")
get_settings.cache_clear()
ok("OLLAMA_CHUNK_TOKENS surchargeable + retombe sur le défaut")

# ─── 2. Fail-fast: missing LLM_PROVIDER ──────────────────────────────────────
section("Config — fail-fast: missing LLM_PROVIDER")
_set_env()
_del_env("LLM_PROVIDER")
try:
    Settings()
    die("ValueError not raised")
except ValueError as exc:
    ok(f"ValueError: {exc}")

# ─── 3. Fail-fast: gemini without GEMINI_API_KEY ─────────────────────────────
section("Config — fail-fast: LLM_PROVIDER=gemini without GEMINI_API_KEY")
_set_env(LLM_PROVIDER="gemini")
_del_env("GEMINI_API_KEY", "GEMINI_MODEL")
try:
    Settings()
    die("ValueError not raised")
except ValueError as exc:
    ok(f"ValueError: {exc}")

# ─── 4. Fail-fast: unknown provider value ────────────────────────────────────
section("Config — fail-fast: LLM_PROVIDER=banana")
_set_env(LLM_PROVIDER="banana")
try:
    Settings()
    die("ValueError not raised")
except ValueError as exc:
    ok(f"ValueError: {exc}")

# ─── 5. Database — init + round-trip ─────────────────────────────────────────
section("Database — init_db + round-trip")
_set_env()

from sqlmodel import Session, create_engine, select  # noqa: E402

from app.core.db import init_db  # noqa: E402
from app.core.enums import BookStatus, Gender, SegmentType  # noqa: E402
from app.models import Book, Chapter, Character, Segment  # noqa: E402

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
test_engine = create_engine(
    f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False}
)
init_db(test_engine)

conn = sqlite3.connect(tmp.name)
tables = {
    r[0]
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
}
conn.close()
for expected in ("book", "chapter", "segment", "character"):
    if expected not in tables:
        die(f"Table '{expected}' missing. Found: {sorted(tables)}")
ok(f"Tables: {sorted(t for t in tables if not t.startswith('sqlite_'))}")

with Session(test_engine) as session:
    book = Book(title="Moby Dick", source_path="/data/moby.epub")
    session.add(book)
    session.commit()
    session.refresh(book)
    assert book.status == BookStatus.PENDING

    chapter = Chapter(
        book_id=book.id, position=1, title="Chapter I", raw_text="Call me Ishmael..."
    )
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    char = Character(
        book_id=book.id, name="Ishmael", gender=Gender.MALE, voice_tone="contemplative"
    )
    session.add(char)
    session.commit()
    session.refresh(char)

    narration = Segment(
        chapter_id=chapter.id,
        position=1,
        text="Call me Ishmael.",
        segment_type=SegmentType.NARRATION,
    )
    dialogue = Segment(
        chapter_id=chapter.id,
        position=2,
        text="Some years ago...",
        segment_type=SegmentType.DIALOGUE,
        character_id=char.id,
    )
    session.add_all([narration, dialogue])
    session.commit()
    char_id = char.id  # capture before session closes

with Session(test_engine) as session:
    b = session.exec(select(Book)).one()
    chapters = session.exec(select(Chapter).where(Chapter.book_id == b.id)).all()
    segments = session.exec(
        select(Segment).where(Segment.chapter_id == chapters[0].id)
    ).all()
    chars = session.exec(select(Character).where(Character.book_id == b.id)).all()

    assert len(chapters) == 1
    assert len(segments) == 2
    assert len(chars) == 1

    dial = next(sg for sg in segments if sg.segment_type == SegmentType.DIALOGUE)
    assert dial.character_id == char_id

    assert chars[0].name == "Ishmael"
    assert chars[0].gender == Gender.MALE

ok("Book -> Chapter -> 2 Segments (narration + dialogue) + Character linked to dialogue")

test_engine.dispose()
os.unlink(tmp.name)
ok("Temp DB cleaned up")

print("\nPHASE 1 OK\n")
