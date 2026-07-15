"""check_phase39.py — Phase 39 : SegmentTake — régénération et sélection de prises.

Contexte : un chapitre est aujourd'hui un WAV monolithique. Cette phase ajoute
SegmentTake (une prise audio par segment) et deux routes :
  - POST .../regenerate   crée un nouveau take + enfile generate_segment
  - POST .../select       sélectionne un take + réassemble le WAV chapitre

Valide :
  - SegmentTake s'importe, les champs attendus sont présents.
  - POST regenerate → 202 + SegmentTake en DB (audio_path=None, is_selected=False).
  - POST select → is_selected basculé, takes concurrents désélectionnés.
  - POST select → WAV chapitre réassemblé (audio_path valide, timings recalculés).
  - POST select avec take d'un autre segment → 422.
  - POST regenerate sur segment inexistant → 404.

Run: .venv/Scripts/python tests/check_phase39.py
"""
import io
import os
import shutil
import sys
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p39.db",
    "HUEY_DB_PATH": "./huey_test_p39.db",
    "DATA_DIR": "./data_test_p39",
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


def _make_wav_bytes(duration_ms: int = 100, sample_rate: int = 22050) -> bytes:
    """WAV silencieux minimal valide."""
    n_frames = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


def _wav_duration_ms(path: str) -> int:
    with wave.open(path, "rb") as w:
        return int(w.getnframes() / w.getframerate() * 1000)


# ── Répertoires de test ───────────────────────────────────────────────────────
_data_dir = Path("data_test_p39")
_takes_dir = _data_dir / "1" / "takes"
_takes_dir.mkdir(parents=True, exist_ok=True)


# ── 1. Imports ────────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")

from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.db import get_session  # noqa: E402
from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import Book, Chapter, Segment, SegmentTake  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ok("SegmentTake importé depuis app.models.entities")

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()

# ── 2. SegmentTake : champs contractuels ──────────────────────────────────────
section("SegmentTake possède les champs attendus")

_fields = SegmentTake.model_fields
check("id", "id" in _fields)
check("segment_id", "segment_id" in _fields)
check("audio_path (Optional)", "audio_path" in _fields)
check("voice_id", "voice_id" in _fields)
check("emotion (Optional)", "emotion" in _fields)
check("is_selected", "is_selected" in _fields)
check("created_at", "created_at" in _fields)
_is_sel_default = getattr(_fields["is_selected"], "default", None)
check("is_selected défaut = False", _is_sel_default is False, f"got {_is_sel_default}")

# ── Helpers DB ────────────────────────────────────────────────────────────────

def _make_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed(session: Session) -> tuple[int, int, int]:
    """Insère Book + Chapter (avec WAV sur disque) + Segment ; retourne leurs ids."""
    ch_wav = _data_dir / "1" / "ch1.wav"
    ch_wav.parent.mkdir(parents=True, exist_ok=True)
    ch_wav.write_bytes(_make_wav_bytes(300))

    book = Book(title="Test", source_path="test.epub", status=BookStatus.DONE)
    session.add(book)
    session.commit()
    session.refresh(book)

    chapter = Chapter(
        book_id=book.id, position=1, raw_text="Texte.",
        status=ChapterStatus.DONE, audio_path=str(ch_wav),
    )
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    seg = Segment(
        chapter_id=chapter.id, position=1,
        text="Bonjour.", segment_type=SegmentType.NARRATION,
        audio_offset_ms=0, duration_ms=300,
    )
    session.add(seg)
    session.commit()
    session.refresh(seg)

    return book.id, chapter.id, seg.id


# ── 3. POST regenerate → 202 + SegmentTake en DB ─────────────────────────────
section("POST .../regenerate → 202, SegmentTake créé (audio_path=None, is_selected=False)")

def _ovr(eng):
    def _dep():
        with Session(eng) as s:
            yield s
    return _dep


_e3 = _make_engine()
app.dependency_overrides[get_session] = _ovr(_e3)
_client = TestClient(app)

with Session(_e3) as _s:
    _bid3, _cid3, _sid3 = _seed(_s)

with patch("app.api.routes.books.generate_segment", lambda take_id: None):
    _r3 = _client.post(
        f"/books/{_bid3}/chapters/1/segments/{_sid3}/regenerate",
        json={"voice_id": "narrator", "emotion": "joyful"},
    )

check("status 202", _r3.status_code == 202, _r3.text)
if _r3.status_code == 202:
    _body3 = _r3.json()
    check("audio_path est None", _body3.get("audio_path") is None)
    check("is_selected est False", _body3.get("is_selected") is False)
    check("voice_id == 'narrator'", _body3.get("voice_id") == "narrator")
    check("emotion == 'joyful'", _body3.get("emotion") == "joyful")
    with Session(_e3) as _sv:
        _takes = _sv.exec(select(SegmentTake).where(SegmentTake.segment_id == _sid3)).all()
    check("1 SegmentTake persisté en DB", len(_takes) == 1, f"got {len(_takes)}")
else:
    fail("champs take + DB count : skipped (route non 202)")

app.dependency_overrides.pop(get_session, None)


# ── 4. POST regenerate sur segment inexistant → 404 ──────────────────────────
section("POST .../regenerate sur segment inexistant → 404")

_e4 = _make_engine()
app.dependency_overrides[get_session] = _ovr(_e4)

with Session(_e4) as _s:
    _bid4, _, _ = _seed(_s)

_r4 = _client.post(
    f"/books/{_bid4}/chapters/1/segments/99999/regenerate",
    json={"voice_id": "narrator"},
)
check("404 sur segment inexistant", _r4.status_code == 404, _r4.text)

app.dependency_overrides.pop(get_session, None)


# ── 5. POST select → bascule is_selected, désélectionne les autres takes ──────
section("POST .../select → bascule is_selected, désélectionne les concurrents")

_e5 = _make_engine()
app.dependency_overrides[get_session] = _ovr(_e5)

with Session(_e5) as _s:
    _bid5, _cid5, _sid5 = _seed(_s)

    _wav_a = _takes_dir / "take5_a.wav"
    _wav_b = _takes_dir / "take5_b.wav"
    _wav_a.write_bytes(_make_wav_bytes(200))
    _wav_b.write_bytes(_make_wav_bytes(150))

    _ta = SegmentTake(segment_id=_sid5, voice_id="narrator", is_selected=True, audio_path=str(_wav_a))
    _tb = SegmentTake(segment_id=_sid5, voice_id="male_0", is_selected=False, audio_path=str(_wav_b))
    _s.add(_ta); _s.add(_tb)
    _s.commit()
    _s.refresh(_ta); _s.refresh(_tb)
    _ta_id, _tb_id = _ta.id, _tb.id

_r5 = _client.post(f"/books/{_bid5}/chapters/1/segments/{_sid5}/takes/{_tb_id}/select")
check("status 200", _r5.status_code == 200, _r5.text)

if _r5.status_code == 200:
    check("take B maintenant is_selected=True", _r5.json().get("is_selected") is True)
    with Session(_e5) as _sv:
        _ta2 = _sv.get(SegmentTake, _ta_id)
        _tb2 = _sv.get(SegmentTake, _tb_id)
    check("take A désélectionné (is_selected=False)", _ta2.is_selected is False)
    check("take B sélectionné (is_selected=True)", _tb2.is_selected is True)
else:
    fail("bascule is_selected : skipped (route non 200)")

app.dependency_overrides.pop(get_session, None)


# ── 6. POST select → WAV chapitre réassemblé, timings recalculés ──────────────
section("POST .../select → chapter WAV réécrit, Segment.audio_offset_ms/duration_ms mis à jour")

_e6 = _make_engine()
app.dependency_overrides[get_session] = _ovr(_e6)

with Session(_e6) as _s:
    _bid6, _cid6, _sid6 = _seed(_s)

    # Second segment
    _seg2 = Segment(
        chapter_id=_cid6, position=2, text="Au revoir.",
        segment_type=SegmentType.NARRATION,
        audio_offset_ms=300, duration_ms=200,
    )
    _s.add(_seg2); _s.commit(); _s.refresh(_seg2)
    _sid6_2 = _seg2.id

    # Take sélectionné pour chaque segment (état initial du chapitre)
    _w1 = _takes_dir / "take6_s1.wav"
    _w2 = _takes_dir / "take6_s2.wav"
    _w1.write_bytes(_make_wav_bytes(200))   # seg1 : 200 ms
    _w2.write_bytes(_make_wav_bytes(150))   # seg2 : 150 ms

    _tk1 = SegmentTake(segment_id=_sid6,   voice_id="narrator", is_selected=True,  audio_path=str(_w1))
    _tk2 = SegmentTake(segment_id=_sid6_2, voice_id="narrator", is_selected=True,  audio_path=str(_w2))
    _s.add(_tk1); _s.add(_tk2); _s.commit()
    _s.refresh(_tk1); _s.refresh(_tk2)

    # Nouveau take pour seg1 (sera sélectionné → durée différente)
    _w1b = _takes_dir / "take6_s1b.wav"
    _w1b.write_bytes(_make_wav_bytes(300))   # 300 ms
    _tk1b = SegmentTake(segment_id=_sid6, voice_id="male_0", is_selected=False, audio_path=str(_w1b))
    _s.add(_tk1b); _s.commit(); _s.refresh(_tk1b)
    _tk1b_id = _tk1b.id

_r6 = _client.post(f"/books/{_bid6}/chapters/1/segments/{_sid6}/takes/{_tk1b_id}/select")
check("status 200", _r6.status_code == 200, _r6.text)

if _r6.status_code == 200:
    with Session(_e6) as _sv:
        _ch6 = _sv.get(Chapter, _cid6)
        _seg1r = _sv.get(Segment, _sid6)
        _seg2r = _sv.get(Segment, _sid6_2)

    _ch_path = Path(_ch6.audio_path) if _ch6.audio_path else None
    check("chapter.audio_path défini", _ch_path is not None)
    if _ch_path:
        check("WAV chapitre présent sur disque", _ch_path.exists(), str(_ch_path))
        if _ch_path.exists():
            # take6_s1b=300 ms + take6_s2=150 ms = 450 ms
            _total = _wav_duration_ms(str(_ch_path))
            check("durée WAV = 450 ms (300+150)", abs(_total - 450) <= 5, f"got {_total} ms")

    check("seg1.audio_offset_ms = 0", _seg1r.audio_offset_ms == 0,
          f"got {_seg1r.audio_offset_ms}")
    check("seg1.duration_ms = 300 (nouveau take)", _seg1r.duration_ms == 300,
          f"got {_seg1r.duration_ms}")
    check("seg2.audio_offset_ms = 300 (décalé après seg1)", _seg2r.audio_offset_ms == 300,
          f"got {_seg2r.audio_offset_ms}")
    check("seg2.duration_ms ≈ 150 (±2 ms rounding)", abs(_seg2r.duration_ms - 150) <= 2,
          f"got {_seg2r.duration_ms}")
else:
    fail("réassemblage : skipped (route non 200)")

app.dependency_overrides.pop(get_session, None)


# ── 7. POST select avec take d'un autre segment → 422 ────────────────────────
section("POST .../select avec take appartenant à un autre segment → 422")

_e7 = _make_engine()
app.dependency_overrides[get_session] = _ovr(_e7)

with Session(_e7) as _s:
    _bid7, _cid7, _sid7 = _seed(_s)

    _seg7b = Segment(
        chapter_id=_cid7, position=2, text="Autre.",
        segment_type=SegmentType.NARRATION,
    )
    _s.add(_seg7b); _s.commit(); _s.refresh(_seg7b)

    _tk7 = SegmentTake(
        segment_id=_seg7b.id, voice_id="narrator", is_selected=False,
        audio_path="/tmp/cross.wav",
    )
    _s.add(_tk7); _s.commit(); _s.refresh(_tk7)
    _tk7_id = _tk7.id

# Tenter de sélectionner le take du seg7b via l'URL de sid7
_r7 = _client.post(
    f"/books/{_bid7}/chapters/1/segments/{_sid7}/takes/{_tk7_id}/select"
)
check("422 sur take cross-segment", _r7.status_code == 422, _r7.text)

app.dependency_overrides.pop(get_session, None)


# ── Nettoyage ─────────────────────────────────────────────────────────────────
for _f in ("scriptvox_test_p39.db", "huey_test_p39.db"):
    try:
        Path(_f).unlink(missing_ok=True)
    except PermissionError:
        pass

shutil.rmtree("data_test_p39", ignore_errors=True)


# ── Résumé ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*52}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
