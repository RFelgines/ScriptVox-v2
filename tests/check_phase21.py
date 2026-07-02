"""check_phase21.py — Phase 21 : timing audio par segment (E0).

Valide :
  - Segment.audio_offset_ms / duration_ms (nouveaux champs SQLModel)
  - SegmentResponse (nouveau schéma Pydantic, avec character_name + voice_id dénormalisés)
  - GET /books/{id}/chapters/{n}/segments (nouvel endpoint)

Run: .venv/Scripts/python tests/check_phase21.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p21.db",
    "HUEY_DB_PATH": "./huey_test_p21.db",
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


# ── 1. Segment.audio_offset_ms / duration_ms existent ─────────────────────────
section("Segment.audio_offset_ms et duration_ms présents sur le modèle SQLModel")
import inspect  # noqa: E402
from app.models.entities import Segment  # noqa: E402

_seg_fields = {name for name, _ in inspect.getmembers(Segment)}
check("audio_offset_ms présent", hasattr(Segment, "audio_offset_ms"),
      "attribut manquant — champ pas encore ajouté au modèle")
check("duration_ms présent", hasattr(Segment, "duration_ms"),
      "attribut manquant — champ pas encore ajouté au modèle")

seg = Segment(chapter_id=1, position=1, text="test")
check("audio_offset_ms nullable par défaut", seg.audio_offset_ms is None,
      f"got {seg.audio_offset_ms!r}")
check("duration_ms nullable par défaut", seg.duration_ms is None,
      f"got {seg.duration_ms!r}")


# ── 2. SegmentResponse expose les bons champs ──────────────────────────────────
section("SegmentResponse : champs id, position, text, segment_type, character_name, voice_id, offsets")
from app.schemas.book import SegmentResponse  # noqa: E402
from app.core.enums import SegmentType  # noqa: E402

_sr_fields = set(SegmentResponse.model_fields.keys())
for _f in ("id", "position", "text", "segment_type", "character_id",
           "character_name", "voice_id", "audio_offset_ms", "duration_ms"):
    check(f"champ '{_f}' présent", _f in _sr_fields, f"champs trouvés : {_sr_fields}")


# ── 3. GET /books/{id}/chapters/{n}/segments — 404 book inconnu ───────────────
section("GET /books/{id}/chapters/{n}/segments : 404 si livre inconnu")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.models.entities import Book, Chapter, Character  # noqa: E402
from app.core.enums import BookStatus  # noqa: E402

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine)


def _rb_session():
    with Session(_engine) as s:
        yield s


app.dependency_overrides[get_session] = _rb_session

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r = _tc.get("/books/99999/chapters/1/segments")
    check("404 si livre inexistant", _r.status_code == 404,
          f"got {_r.status_code}")


# ── 4. GET /books/{id}/chapters/{n}/segments — 404 chapitre inconnu ───────────
section("GET /books/{id}/chapters/{n}/segments : 404 si chapitre inexistant")

with Session(_engine) as _s:
    _b = Book(title="Test", source_path="/tmp/t.epub", status=BookStatus.ANALYZED)
    _s.add(_b)
    _s.commit()
    _book_id = _b.id

with TestClient(app, raise_server_exceptions=False) as _tc:
    _r2 = _tc.get(f"/books/{_book_id}/chapters/99/segments")
    check("404 si chapitre inexistant", _r2.status_code == 404,
          f"got {_r2.status_code}")


# ── 5. GET /books/{id}/chapters/{n}/segments — happy path ─────────────────────
section("GET /books/{id}/chapters/{n}/segments : 200 + SegmentResponse avec timing")

with Session(_engine) as _s:
    _ch = Chapter(book_id=_book_id, position=1, title="Ch1", raw_text="test")
    _s.add(_ch)
    _s.commit()
    _ch_id = _ch.id

    _char = Character(book_id=_book_id, name="Alice", gender="FEMALE", voice_id="female_0")
    _s.add(_char)
    _s.commit()
    _char_id = _char.id

    _s.add(Segment(
        chapter_id=_ch_id, position=1, text="Il était une fois.",
        segment_type=SegmentType.NARRATION,
        audio_offset_ms=0, duration_ms=1200,
    ))
    _s.add(Segment(
        chapter_id=_ch_id, position=2, text="Bonjour !",
        segment_type=SegmentType.DIALOGUE,
        character_id=_char_id,
        audio_offset_ms=1200, duration_ms=800,
    ))
    _s.commit()

with TestClient(app) as _tc:
    _r3 = _tc.get(f"/books/{_book_id}/chapters/1/segments")
    check("200 OK", _r3.status_code == 200, f"got {_r3.status_code} {_r3.text[:200]}")

_segs = _r3.json()
check("2 segments retournés", len(_segs) == 2, f"got {len(_segs)}")

_s0, _s1 = _segs[0], _segs[1]
check("position 1 = narration", _s0["segment_type"] == "NARRATION")
check("position 1 : character_name=None (narration)", _s0["character_name"] is None)
# voice_id doit refléter la voix réellement utilisée à la synthèse (chapter.py
# résout toujours la narration sur NARRATOR_VOICE_ID), pas rester None — sinon
# le frontend ("Lu par") n'a aucun moyen de savoir quelle voix lit la narration.
check("position 1 : voice_id='narrator' (voix réellement utilisée à la synthèse)",
      _s0["voice_id"] == "narrator", f"got {_s0['voice_id']!r}")
check("position 1 : audio_offset_ms=0", _s0["audio_offset_ms"] == 0)
check("position 1 : duration_ms=1200", _s0["duration_ms"] == 1200)

check("position 2 = dialogue", _s1["segment_type"] == "DIALOGUE")
check("position 2 : character_name='Alice' (dénormalisé)", _s1["character_name"] == "Alice",
      f"got {_s1['character_name']!r}")
check("position 2 : voice_id='female_0' (dénormalisé)", _s1["voice_id"] == "female_0",
      f"got {_s1['voice_id']!r}")
check("position 2 : audio_offset_ms=1200", _s1["audio_offset_ms"] == 1200)
check("position 2 : duration_ms=800", _s1["duration_ms"] == 800)


# ── 6. GET .../segments — personnage sans voice_id assigné -> fallback narrator ─
section("GET .../segments : personnage sans voice_id -> voice_id='narrator' (comme à la synthèse)")

with Session(_engine) as _s:
    _ch6 = Chapter(book_id=_book_id, position=2, title="Ch2", raw_text="test")
    _s.add(_ch6)
    _s.commit()
    _ch6_id = _ch6.id

    _char6 = Character(book_id=_book_id, name="Bob", gender="MALE", voice_id=None)
    _s.add(_char6)
    _s.commit()
    _char6_id = _char6.id

    _s.add(Segment(
        chapter_id=_ch6_id, position=1, text="Salut.",
        segment_type=SegmentType.DIALOGUE,
        character_id=_char6_id,
        audio_offset_ms=0, duration_ms=500,
    ))
    _s.commit()

with TestClient(app) as _tc6:
    _r6 = _tc6.get(f"/books/{_book_id}/chapters/2/segments")
    check("200 OK", _r6.status_code == 200, f"got {_r6.status_code} {_r6.text[:200]}")

_segs6 = _r6.json()
check("1 segment retourné", len(_segs6) == 1, f"got {len(_segs6)}")
check("character_name='Bob' (dénormalisé malgré l'absence de voice_id)",
      _segs6[0]["character_name"] == "Bob", f"got {_segs6[0]['character_name']!r}")
check("voice_id='narrator' (fallback -- même règle qu'à la synthèse)",
      _segs6[0]["voice_id"] == "narrator", f"got {_segs6[0]['voice_id']!r}")


# ── Cleanup ────────────────────────────────────────────────────────────────────
app.dependency_overrides.clear()
_engine.dispose()
for leftover in ("scriptvox_test_p21.db", "huey_test_p21.db"):
    try:
        if os.path.exists(leftover):
            os.remove(leftover)
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
