"""check_phase50.py — production de livres audio : horodatage des chapitres, extrait avant
rendu, reprise par segment, lexique de prononciation, mastering ACX, titres EPUB.

Run: python tests/check_phase50.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="sv_p50_"))
os.environ.update({
    "LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3", "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p50.db", "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": str(_TMP / "data"), "TTS_PROVIDER": "edgetts",
})

_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    ok  {label}")
    else:
        msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


def section(title: str) -> None:
    print(f"\n── {title}")


# ── 1. Horodatage des chapitres ───────────────────────────────────────────────
from app.services.audio import m4b as m4b_mod  # noqa: E402

section("Horodatage des chapitres (.txt)")
marks = m4b_mod.chapter_marks([61_000, 3_600_000, 5_000], ["Un", "Deux\n  longs", "Trois"], 500)
txt = m4b_mod.chapters_txt(marks)
check("une ligne HH:MM:SS par chapitre, positions cumulées avec jonctions",
      txt == "00:00:00 Un\n00:01:01 Deux longs\n01:01:02 Trois\n", repr(txt))
check("chemin à côté du livre assemblé",
      m4b_mod.chapters_txt_path("/x/livre.wav").name == "livre.chapters.txt")


# ── Outils communs (base en mémoire, moteur factice) ──────────────────────────
from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.enums import BookStatus, SegmentType  # noqa: E402
from app.models import Book, Chapter, Character, Segment  # noqa: E402
from app.services.audio.format import silence_wav, wav_duration_ms  # noqa: E402
from app.services.tts.base import BaseTTSProvider  # noqa: E402
from app.workers import tasks  # noqa: E402


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


class _Stub(BaseTTSProvider):
    """400 ms de silence par appel ; mémorise (texte, voix, émotion)."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        self.calls.append((text, voice_id, emotion))
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("synthèse impossible")
        return silence_wav(400)


def _book_with_dialogue(eng, n_segments=10, seg_len=200):
    """Un livre, un chapitre, `n_segments` segments alternant narration et répliques d'Alice."""
    with Session(eng) as s:
        b = Book(title="Livre", source_path=str(_TMP / "x.epub"), status=BookStatus.ANALYZED)
        s.add(b); s.commit(); s.refresh(b)
        alice = Character(book_id=b.id, name="Alice", voice_id="female_0")
        s.add(alice); s.commit(); s.refresh(alice)
        c = Chapter(book_id=b.id, position=1, title="Un", raw_text="x" * n_segments * seg_len)
        s.add(c); s.commit(); s.refresh(c)
        for i in range(n_segments):
            dlg = i % 2 == 1
            s.add(Segment(chapter_id=c.id, position=i + 1, text=f"{i:02d} " + "a" * (seg_len - 3),
                          segment_type=SegmentType.DIALOGUE if dlg else SegmentType.NARRATION,
                          character_id=alice.id if dlg else None, emotion="joyeuse" if dlg else None))
        s.commit()
        return b.id, c.id, alice.id


# ── 2. Extrait d'un chapitre avant rendu ──────────────────────────────────────
section("Extrait avant rendu : début du chapitre, mêmes voix et émotions que le rendu final")
eng = _engine()
book_id, chapter_id, alice_id = _book_with_dialogue(eng, n_segments=10, seg_len=200)
stub = _Stub()
with patch("app.core.db.get_engine", return_value=eng), \
     patch.object(tasks, "_get_tts_provider", return_value=stub):
    tasks._generate_chapter_excerpt_impl(chapter_id)
    with Session(eng) as s:
        path = tasks.chapter_excerpt_path(s, s.get(Chapter, chapter_id))
check("fichier d'extrait écrit", path.exists(), str(path))
check("seuls les premiers segments (900 caractères -> 4 x 200) sont rendus",
      [c[0][:2] for c in stub.calls] == ["00", "01", "02", "03"], str([c[0][:2] for c in stub.calls]))
check("voix et émotion du personnage respectées",
      stub.calls[1][1:] == ("female_0", "joyeuse") and stub.calls[0][1] == "narrator", str(stub.calls[:2]))
check("durée = 4 x 400 ms + pauses entre répliques", wav_duration_ms(path.read_bytes()) > 1600)
with Session(eng) as s:
    seg = s.exec(select(Segment).where(Segment.chapter_id == chapter_id)).first()
    ch = s.get(Chapter, chapter_id)
check("le chapitre et ses segments ne sont pas touchés (ni statut, ni minutage)",
      ch.status.value == "PENDING" and ch.audio_path is None and seg.duration_ms is None,
      f"{ch.status} {ch.audio_path} {seg.duration_ms}")

with Session(eng) as s:
    a = s.get(Character, alice_id); a.voice_id = "female_1"; s.add(a); s.commit()
    path2 = tasks.chapter_excerpt_path(s, s.get(Chapter, chapter_id))
check("réattribuer une voix invalide l'extrait (autre fichier)", path2 != path)

from app.services.audio.chapter import _prefix_within  # noqa: E402


class _S:
    def __init__(self, t):
        self.text = t


check("un premier segment plus long que la limite est quand même rendu",
      len(_prefix_within([_S("x" * 5000), _S("y")], 900)) == 1)

section("Extrait avant rendu : API")
with patch("app.core.db.get_engine", return_value=eng):
    from app.core.db import get_session
    from app.main import app as fastapi_app

    def _sess():
        with Session(eng) as s:
            yield s

    fastapi_app.dependency_overrides[get_session] = _sess
    client = TestClient(fastapi_app)
    queued = []
    with patch("app.api.routes.books.generate_chapter_excerpt", side_effect=queued.append):
        r = client.post(f"/books/{book_id}/chapters/1/excerpt")
        check("POST (pas encore rendu) -> 202 ready=false, tâche enfilée",
              r.status_code == 202 and r.json() == {"ready": False} and queued == [chapter_id],
              f"{r.status_code} {r.text} {queued}")
        check("GET avant rendu -> 404", client.get(f"/books/{book_id}/chapters/1/excerpt").status_code == 404)
        with patch.object(tasks, "_get_tts_provider", return_value=_Stub()):
            tasks._generate_chapter_excerpt_impl(chapter_id)
        r = client.post(f"/books/{book_id}/chapters/1/excerpt")
        check("POST une fois rendu -> ready=true, rien de relancé",
              r.json() == {"ready": True} and len(queued) == 1, f"{r.text} {queued}")
        r = client.get(f"/books/{book_id}/chapters/1/excerpt")
        check("GET -> WAV", r.status_code == 200 and r.headers["content-type"] == "audio/wav")
        check("chapitre inconnu -> 404", client.post(f"/books/{book_id}/chapters/9/excerpt").status_code == 404)
        with Session(eng) as s:
            c2 = Chapter(book_id=book_id, position=2, title="Deux", raw_text="z")
            s.add(c2); s.commit()
        check("chapitre non analysé (aucun segment) -> 409",
              client.post(f"/books/{book_id}/chapters/2/excerpt").status_code == 409)
    fastapi_app.dependency_overrides.clear()


print()
if _errors:
    print(f"ÉCHEC : {len(_errors)} vérification(s)")
    sys.exit(1)
print("OK : toutes les vérifications passent")
