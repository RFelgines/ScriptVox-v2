"""check_phase48.py — audit 2026-09-25, lot worker/API : génération de livre par la file de
chapitres, progression, chapitres exclus, M4B, aperçu de voix, EPUB (sommaire, bombe zip),
attribution des voix par importance, SQLite WAL.

Run: python tests/check_phase48.py
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="sv_p48_"))
os.environ.update({
    "LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3", "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p48.db", "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": str(_TMP / "data"), "TTS_PROVIDER": "edgetts",
    "AUDIO_PAUSE_SAME_VOICE_MS": "0", "AUDIO_PAUSE_VOICE_CHANGE_MS": "0",
    "AUDIO_PAUSE_CHAPTER_MS": "500", "AUDIO_NORMALIZE": "false",
})

_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    ok  {label}")
    else:
        msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.enums import BookStatus, ChapterStatus, Gender, SegmentType  # noqa: E402
from app.models import Book, Chapter, Character, Segment  # noqa: E402
from app.services.audio.format import silence_wav, wav_duration_ms  # noqa: E402
from app.services.tts.base import BaseTTSProvider  # noqa: E402
from app.workers import tasks  # noqa: E402


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


class _Stub(BaseTTSProvider):
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("synthèse impossible")
        return silence_wav(1000)


def _book(eng, chapters, status=BookStatus.ANALYZED, cover=None):
    """chapters : [(titre, texte, included)]"""
    src = _TMP / f"book{len(list(_TMP.glob('book*.epub')))}.epub"
    with Session(eng) as s:
        b = Book(title="Mon livre", author="Moi", source_path=str(src), status=status, cover_path=cover)
        s.add(b); s.commit(); s.refresh(b)
        for i, (title, text, inc) in enumerate(chapters, start=1):
            c = Chapter(book_id=b.id, position=i, title=title, raw_text=text, included=inc)
            s.add(c); s.commit(); s.refresh(c)
            s.add(Segment(chapter_id=c.id, position=1, text=text, segment_type=SegmentType.NARRATION))
            s.commit()
        return b.id


print("[1] génération d'un livre par la file de chapitres")
eng = _engine()
book_id = _book(eng, [("Un", "Premier chapitre.", True), ("Couverture", "cover", False), ("Deux", "Second chapitre.", True)])
stub = _Stub()
enqueued = {"n": 0}

def _fake_pump_task():
    enqueued["n"] += 1

with patch("app.core.db.get_engine", return_value=eng), \
     patch("app.services.tts.factory.get_tts_provider", return_value=stub), \
     patch.object(tasks, "generate_chapter_queue_pump", _fake_pump_task):
    tasks._enqueue_book_generation(book_id)
    with Session(eng) as s:
        b = s.get(Book, book_id)
        chs = {c.position: c for c in s.exec(select(Chapter).where(Chapter.book_id == book_id))}
    check("1er chapitre traité en ligne, le livre reste GENERATING", b.status == BookStatus.GENERATING, str(b.status))
    check("une tâche de pompe ré-enfilée pour la suite (une tâche par chapitre)", enqueued["n"] == 1, str(enqueued))
    check("chapitre exclu jamais mis en file ni traité",
          chs[2].status == ChapterStatus.PENDING and chs[2].queued_at is None and "cover" not in stub.calls)
    check("étape et progression pondérée publiées", b.stage == "generation" and 0 < b.stage_progress < 100,
          f"{b.stage} {b.stage_progress}")
    check("durée du chapitre enregistrée", chs[1].duration_ms == 1000, str(chs[1].duration_ms))
    while True:  # le worker traite la tâche suivante
        with Session(eng) as s:
            left = s.exec(select(Chapter).where(Chapter.status == ChapterStatus.PENDING,
                                                Chapter.queued_at.is_not(None))).first()
        if left is None:
            break
        tasks._generate_chapter_queue_pump_impl(limit=1)
with Session(eng) as s:
    b = s.get(Book, book_id)
check("livre DONE une fois tous les chapitres inclus faits", b.status == BookStatus.DONE, f"{b.status} {b.error_message}")
check("WAV, MP3 assemblés", b.audio_path and Path(b.audio_path).exists() and b.mp3_path and Path(b.mp3_path).exists())
check("durée du livre = 2 x 1 s + 0,5 s de jonction (chapitre exclu absent)",
      abs(wav_duration_ms(Path(b.audio_path).read_bytes()) - 2500) < 20, str(wav_duration_ms(Path(b.audio_path).read_bytes())))
import shutil  # noqa: E402
if shutil.which("ffmpeg"):
    check("M4B produit", b.m4b_path and Path(b.m4b_path).exists(), str(b.m4b_path))
    import subprocess
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "compact", b.m4b_path],
                           capture_output=True, text=True).stdout
    check("M4B : 2 chapitres (le chapitre exclu n'y figure pas)", probe.count("chapter|") == 2, probe)
check("étape remise à zéro, progression 100", b.stage is None and b.progress == 100.0 and b.eta_seconds is None)

print("\n[2] échec d'un chapitre -> livre FAILED, reprise conservant les chapitres faits")
eng2 = _engine()
bid2 = _book(eng2, [("A", "Bon.", True), ("B", "Mauvais texte.", True)])
stub2 = _Stub(fail_on="Mauvais")
import app.services.audio.chapter as chmod  # noqa: E402
chmod._TTS_RETRY_DELAY = 0
with patch("app.core.db.get_engine", return_value=eng2), \
     patch("app.services.tts.factory.get_tts_provider", return_value=stub2), \
     patch.object(tasks, "generate_chapter_queue_pump", _fake_pump_task):
    tasks._enqueue_book_generation(bid2)
    tasks._generate_chapter_queue_pump_impl()
with Session(eng2) as s:
    b2 = s.get(Book, bid2)
    chs2 = {c.position: c for c in s.exec(select(Chapter).where(Chapter.book_id == bid2))}
check("livre FAILED, étape = génération", b2.status == BookStatus.FAILED and b2.failed_stage == "generation", str(b2.status))
check("message d'erreur du chapitre remonté", "synthèse impossible" in (b2.error_message or ""), str(b2.error_message))
check("le chapitre réussi reste DONE", chs2[1].status == ChapterStatus.DONE)
stub2b = _Stub()
with patch("app.core.db.get_engine", return_value=eng2), \
     patch("app.services.tts.factory.get_tts_provider", return_value=stub2b), \
     patch.object(tasks, "generate_chapter_queue_pump", _fake_pump_task):
    tasks._enqueue_book_generation(bid2)  # reprise
    tasks._generate_chapter_queue_pump_impl()
with Session(eng2) as s:
    b2 = s.get(Book, bid2)
check("reprise : seul le chapitre en échec est refait", stub2b.calls == ["Mauvais texte."], str(stub2b.calls))
check("reprise : livre DONE", b2.status == BookStatus.DONE, f"{b2.status} {b2.error_message}")

print("\n[3] bouton Arrêter : la file du livre est vidée")
from fastapi.testclient import TestClient  # noqa: E402
from app.core import db as dbmod  # noqa: E402
eng3 = _engine()
dbmod._engine = eng3
from app.main import app  # noqa: E402
client = TestClient(app)
bid3 = _book(eng3, [("A", "a", True), ("B", "b", True)], status=BookStatus.GENERATING)
with Session(eng3) as s:
    from datetime import datetime, timezone
    for c in s.exec(select(Chapter).where(Chapter.book_id == bid3)):
        c.queued_at = datetime.now(timezone.utc); s.add(c)
    s.commit()
r = client.post(f"/books/{bid3}/stop")
check("POST /stop -> 200", r.status_code == 200, r.text)
with Session(eng3) as s:
    left = s.exec(select(Chapter).where(Chapter.book_id == bid3, Chapter.queued_at.is_not(None))).all()
check("plus aucun chapitre en file après l'arrêt", not left)

print("\n[4] API : chapitre inclus/exclu, durée, M4B")
bid4 = _book(eng3, [("A", "a" * 400, True)], status=BookStatus.DONE)
r = client.patch(f"/books/{bid4}/chapters/1", json={"included": False})
check("PATCH chapitre included=false", r.status_code == 200 and r.json()["included"] is False, r.text)
check("GET chapitres expose included + duration_ms", "included" in client.get(f"/books/{bid4}/chapters").json()[0])
check("chapitre inconnu -> 404", client.patch(f"/books/{bid4}/chapters/9", json={"included": True}).status_code == 404)
check("M4B absent -> 404 explicite", client.get(f"/books/{bid4}/audio/m4b").status_code == 404)
m4b_file = _TMP / "x.m4b"; m4b_file.write_bytes(b"fake")
with Session(eng3) as s:
    bb = s.get(Book, bid4); bb.m4b_path = str(m4b_file); s.add(bb); s.commit()
check("M4B servi quand présent", client.get(f"/books/{bid4}/audio/m4b").status_code == 200)
check("BookResponse expose stage / eta / m4b_path", {"stage", "eta_seconds", "m4b_path"} <= set(client.get(f"/books/{bid4}").json()))

print("\n[4b] chapitres exclus : jamais exigés, jamais mis en file")
bid4b = _book(eng3, [("Couv", "c", False), ("A", "a" * 400, True), ("B", "b" * 400, True)], status=BookStatus.ANALYZED)
with Session(eng3) as s_:
    ex = s_.exec(select(Chapter).where(Chapter.book_id == bid4b, Chapter.position == 1)).first()
    seg = s_.exec(select(Segment).where(Segment.chapter_id == ex.id)).first()
    s_.delete(seg); s_.commit()   # un chapitre exclu n'a jamais de segments
import app.api.routes.books as _books_routes  # noqa: E402
_books_routes.generate_book = lambda *a, **k: None
r = client.post(f"/books/{bid4b}/generate")
check("livre analysé dont un chapitre exclu n'a pas de segments -> génération acceptée (202)", r.status_code == 202, r.text)
r = client.post(f"/books/{bid4b}/chapters/1/generate")
check("génération d'un chapitre exclu -> 409", r.status_code == 409, r.text)
_books_routes.generate_chapter_queue_pump = lambda: None
r = client.post(f"/books/{bid4b}/chapters/generate")
with Session(eng3) as s_:
    queued = {c.position: c.queued_at is not None for c in s_.exec(select(Chapter).where(Chapter.book_id == bid4b))}
check("« tout générer » ignore les chapitres exclus", queued == {1: False, 2: True, 3: True}, str(queued))

print("\n[5] progression et temps restant")
tasks._THROUGHPUT.clear()
check("pas d'ETA sans mesure", tasks._eta_seconds(1, "generation", 1000) is None)
tasks._record_throughput(1, "generation", 1000, 10.0)
tasks._record_throughput(1, "generation", 1000, 10.0)
check("ETA = restant / débit (100 c/s -> 500 c = 5 s)", tasks._eta_seconds(1, "generation", 500) == 5)

print("\n[6] aperçu d'une voix sur une réplique du personnage")
eng6 = _engine()
dbmod._engine = eng6
with Session(eng6) as s:
    b = Book(title="P", source_path="x", language="fr"); s.add(b); s.commit(); s.refresh(b)
    c = Chapter(book_id=b.id, position=1, raw_text="x"); s.add(c); s.commit(); s.refresh(c)
    ch = Character(book_id=b.id, name="Hagrid", gender=Gender.MALE, voice_id="male_0"); s.add(ch); s.commit(); s.refresh(ch)
    s.add(Segment(chapter_id=c.id, position=1, text="Court.", segment_type=SegmentType.DIALOGUE, character_id=ch.id))
    s.add(Segment(chapter_id=c.id, position=2, text="Harry, t'es un sorcier. Et un sacré !", segment_type=SegmentType.DIALOGUE, character_id=ch.id))
    s.add(Segment(chapter_id=c.id, position=3, text="Une narration très très très longue qui ne compte pas.", segment_type=SegmentType.NARRATION))
    s.commit()
    char_id = ch.id
    check("la réplique la plus longue du personnage est choisie", tasks._preview_text(s, ch).startswith("Harry, t'es un sorcier."))
    p1 = tasks.character_preview_path(s, ch, "male_1")
    p2 = tasks.character_preview_path(s, ch, "male_1")
    check("chemin d'aperçu stable", p1 == p2 and p1.suffix == ".wav")
    from app.models import AppSetting
    s.add(AppSetting(id=1, tts_options='{"model": "autre"}')); s.commit()
    check("changer de moteur invalide l'aperçu (empreinte du chemin)", tasks.character_preview_path(s, ch, "male_1") != p1)
enq = []
with patch("app.workers.tasks.generate_character_preview", lambda cid, vid: enq.append((cid, vid))):
    client6 = TestClient(app)
    r = client6.post(f"/characters/{char_id}/preview", json={"voice_id": "male_1"})
    check("POST preview -> 202 + tâche enfilée", r.status_code == 202 and r.json() == {"ready": False} and enq == [(char_id, "male_1")], r.text)
    check("voix invalide -> 422", client6.post(f"/characters/{char_id}/preview", json={"voice_id": "nope"}).status_code == 422)
    check("GET avant génération -> 404", client6.get(f"/characters/{char_id}/preview", params={"voice_id": "male_1"}).status_code == 404)
    with patch("app.core.db.get_engine", return_value=eng6), patch("app.services.tts.factory.get_tts_provider", return_value=_Stub()):
        tasks._generate_character_preview_impl(char_id, "male_1")
    r = client6.get(f"/characters/{char_id}/preview", params={"voice_id": "male_1"})
    check("aperçu généré puis servi", r.status_code == 200 and r.content[:4] == b"RIFF")
    check("2e POST : déjà prêt, rien relancé", client6.post(f"/characters/{char_id}/preview", json={"voice_id": "male_1"}).json() == {"ready": True} and len(enq) == 1)

print("\n[7] EPUB : sommaire, pages non narratives, bombe de décompression")
from ebooklib import epub  # noqa: E402
from app.services.epub.parser import EpubParser  # noqa: E402


def _make_epub(path, chapters):
    book = epub.EpubBook()
    book.set_identifier("id"); book.set_title("Roman"); book.set_language("fr"); book.add_author("Moi")
    items = []
    for i, (fname, title, text) in enumerate(chapters):
        c = epub.EpubHtml(title=title, file_name=fname, lang="fr")
        c.content = f"<html><body><p>{text}</p></body></html>"
        book.add_item(c); items.append(c)
    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.spine = items
    epub.write_epub(str(path), book)

real = "Il était une fois un long récit. " * 200
_make_epub(_TMP / "real.epub", [
    ("cover.xhtml", "Couverture", "Couv"),
    ("copyright.xhtml", "Mentions légales", "Tous droits réservés " * 30),
    ("ch1.xhtml", "Le début", real),
    ("ch2.xhtml", "Trop court", "Bref."),
    ("ch3.xhtml", "La fin", real),
])
pb = EpubParser().parse(str(_TMP / "real.epub"))
inc = {c.position: c.included for c in pb.chapters}
check("couverture et copyright exclus, chapitres réels inclus", inc == {1: False, 2: False, 3: True, 4: False, 5: True}, str(inc))
check("titres issus de la table des matières EPUB", [c.title for c in pb.chapters][2] == "Le début", str([c.title for c in pb.chapters]))
small = EpubParser().parse(str(ROOT / "tests" / "fixtures" / "test.epub"))
check("un livre entièrement court n'est jamais vidé de son contenu", all(c.included for c in small.chapters))

# Plusieurs chapitres dans UN fichier (EPUB Projet Gutenberg) : découpe selon les ancres du sommaire
multi = epub.EpubBook()
multi.set_identifier("m"); multi.set_title("Recueil"); multi.set_language("fr")
hdr = epub.EpubHtml(title="h", file_name="pg-header.xhtml"); hdr.content = "<html><body><p>The Project Gutenberg eBook of Recueil</p></body></html>"
body = epub.EpubHtml(title="b", file_name="body.xhtml")
body.content = ("<html><body><h2 id='a1'>Premier conte</h2>" + "<p>" + real + "</p>"
                + "<h2 id='a2'>Second conte</h2>" + "<p>" + real + "</p></body></html>")
lic = epub.EpubHtml(title="l", file_name="pg-footer.xhtml"); lic.content = "<html><body><p>" + ("License text " * 400) + "</p></body></html>"
for it in (hdr, body, lic):
    multi.add_item(it)
multi.toc = (epub.Link("body.xhtml#a1", "Premier conte", "a1"), epub.Link("body.xhtml#a2", "Second conte", "a2"),
             epub.Link("pg-footer.xhtml#f", "THE FULL PROJECT GUTENBERG LICENSE", "f"))
multi.add_item(epub.EpubNcx()); multi.spine = [hdr, body, lic]
epub.write_epub(str(_TMP / "multi.epub"), multi)
pm = EpubParser().parse(str(_TMP / "multi.epub"))
kept = [c.title for c in pm.chapters if c.included]
check("un fichier à 2 ancres du sommaire -> 2 chapitres", kept == ["Premier conte", "Second conte"], str([(c.title, c.included) for c in pm.chapters]))
check("en-tête et licence Gutenberg exclus", all(not c.included for c in pm.chapters if c.title not in ("Premier conte", "Second conte")))
check("aucun texte perdu à la découpe", sum(len(c.raw_text) for c in pm.chapters if c.included) >= 2 * len(real.strip()) - 10)

bomb = _TMP / "bomb.epub"
with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("mimetype", "application/epub+zip")
    z.writestr("big.txt", b"\x00" * (60 * 1024 * 1024))
try:
    EpubParser().parse(str(bomb))
    check("taux de compression suspect refusé", False)
except ValueError as exc:
    check("taux de compression suspect refusé", "compression" in str(exc), str(exc))
many = _TMP / "many.epub"
with zipfile.ZipFile(many, "w") as z:
    for i in range(5100):
        z.writestr(f"f{i}.txt", "x")
try:
    EpubParser().parse(str(many))
    check("trop de fichiers refusé", False)
except ValueError as exc:
    check("trop de fichiers refusé", "fichiers" in str(exc))

print("\n[8] attribution des voix : les personnages importants choisissent d'abord")
from app.services.voice_assignment import assign_voices, seed_catalogue_voices  # noqa: E402
eng8 = _engine()
with Session(eng8) as s:
    seed_catalogue_voices(s)
    b = Book(title="V", source_path="x"); s.add(b); s.commit(); s.refresh(b)
    c = Chapter(book_id=b.id, position=1, raw_text="x"); s.add(c); s.commit(); s.refresh(c)
    names = ["Argus", "Bane", "Harry"]
    chars = []
    for n in names:
        ch = Character(book_id=b.id, name=n, gender=Gender.MALE); s.add(ch); s.commit(); s.refresh(ch); chars.append(ch)
    counts = {"Argus": 1, "Bane": 2, "Harry": 50}
    pos = 0
    for ch in chars:
        for _ in range(counts[ch.name]):
            pos += 1
            s.add(Segment(chapter_id=c.id, position=pos, text="t", segment_type=SegmentType.DIALOGUE, character_id=ch.id))
    s.commit()
    assign_voices(b.id, s)
    got = {ch.name: s.get(Character, ch.id).voice_id for ch in chars}
    from app.services.voice_assignment import VOICE_CATALOGUE, _score_voice
    best = sorted(VOICE_CATALOGUE[Gender.MALE], key=lambda v: (-_score_voice(chars[2], v), v))[0]
    check("le héros (50 répliques) obtient la meilleure voix disponible", got["Harry"] == best, str(got))
    check("voix toutes distinctes (3 personnages, 3 voix masculines)", len(set(got.values())) == 3, str(got))

print("\n[8b] Book.updated_at rafraîchi à chaque modification")
eng8b = _engine()
with Session(eng8b) as s_:
    bk = Book(title="U", source_path="x"); s_.add(bk); s_.commit(); s_.refresh(bk)
    first = bk.updated_at
    import time as _t; _t.sleep(0.01)
    bk.title = "U2"; s_.add(bk); s_.commit(); s_.refresh(bk)
    check("updated_at avance après modification", bk.updated_at > first, f"{first} -> {bk.updated_at}")

print("\n[9] SQLite en mode WAL")
from app.core.db import _enable_sqlite_pragmas  # noqa: E402
fe = create_engine(f"sqlite:///{_TMP}/wal.db")
_enable_sqlite_pragmas(fe)
with fe.connect() as c:
    mode = c.exec_driver_sql("PRAGMA journal_mode").scalar()
    bt = c.exec_driver_sql("PRAGMA busy_timeout").scalar()
check("journal_mode = wal", mode == "wal", str(mode))
check("busy_timeout = 5000 ms", bt == 5000, str(bt))

print()
if _errors:
    print(f"{len(_errors)} échec(s)")
    sys.exit(1)
print("Tous les tests OK")
