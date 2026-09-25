"""check_phase45.py — audit 2026-09-25, lot 1 : bugs de file de chapitres et de résolution de noms.

Verifie :
  - BUG-1 : un chapitre DONE / FAILED remis en file repasse PENDING et est bien traité par la pompe ;
            la génération par chapitre est acceptée pour un livre DONE / FAILED.
  - BUG-2 : _resolve_character_name est déterministe (mêmes résultats sous plusieurs
            PYTHONHASHSEED), refuse l'ambigu et les mots-titres seuls.

Run: python tests/check_phase45.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="sv_p45_")
os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p45.db",
    "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": f"{_TMP}/data",
    "TTS_PROVIDER": "edgetts",
})

_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    ok  {label}")
    else:
        msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


print("[1] BUG-2 : résolution de noms déterministe")
from app.services.llm.base import _resolve_character_name  # noqa: E402

fam = {"Ron Weasley", "Ginny Weasley", "Molly Weasley"}
check("nom de famille ambigu -> None", _resolve_character_name("Weasley", fam) is None)
check("prénom unique -> résolu",
      _resolve_character_name("Percy", {"Percy Weasley", "Ron Weasley"}) == "Percy Weasley")
check("titre seul -> None",
      _resolve_character_name("Professeur", {"Professeur McGonagall", "Professeur Rogue"}) is None)
check("égalité stricte prioritaire",
      _resolve_character_name("Mr Dursley", {"Mr Dursley", "Dudley Dursley"}) == "Mr Dursley")
check("nom inconnu -> None", _resolve_character_name("Hagrid", fam) is None)

code = (
    "import sys; sys.path.insert(0,'.');"
    "from app.services.llm.base import _resolve_character_name as r;"
    "print(r('Weasley',{'Ron Weasley','Ginny Weasley'}), r('Rogue',{'Professeur Rogue','Severus Rogue'}))"
)
outs = set()
for seed in ("1", "2", "3", "4", "5"):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    outs.add(subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True).stdout.strip())
check("identique sous 5 PYTHONHASHSEED", len(outs) == 1, f"{outs}")

print("\n[2] BUG-1 : re-file d'un chapitre DONE / FAILED")
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core import db as dbmod  # noqa: E402
from app.core.enums import BookStatus, ChapterStatus  # noqa: E402
from app.models import Book, Chapter  # noqa: E402

eng = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(eng)
dbmod._engine = eng

import app.api.routes.books as books_routes  # noqa: E402
from app.workers import tasks  # noqa: E402

pumped: list[int] = []
books_routes.generate_chapter_queue_pump = lambda: None  # ne pas passer par Huey


def _stub(chapter_id: int) -> None:
    pumped.append(chapter_id)
    with Session(eng) as s:
        c = s.get(Chapter, chapter_id)
        c.status = ChapterStatus.DONE
        c.queued_at = None
        s.add(c)
        s.commit()


tasks._generate_chapter_impl = _stub

from app.main import app  # noqa: E402

with Session(eng) as s:
    b = Book(title="t", source_path="x", status=BookStatus.DONE)
    s.add(b)
    s.commit()
    s.refresh(b)
    book_id = b.id
    for pos, st in [(1, ChapterStatus.DONE), (2, ChapterStatus.FAILED), (3, ChapterStatus.PENDING)]:
        s.add(Chapter(book_id=book_id, position=pos, raw_text="x", status=st,
                      error_message="boom" if st == ChapterStatus.FAILED else None))
    s.commit()

client = TestClient(app)
r1 = client.post(f"/books/{book_id}/chapters/1/generate")
r2 = client.post(f"/books/{book_id}/chapters/2/generate")
check("régénération chapitre DONE sur livre DONE acceptée (202)", r1.status_code == 202, r1.text)
check("re-file chapitre FAILED acceptée (202)", r2.status_code == 202, r2.text)
with Session(eng) as s:
    chs = {c.position: c for c in s.exec(select(Chapter).where(Chapter.book_id == book_id))}
check("chapitre 1 repassé PENDING + queued_at", chs[1].status == ChapterStatus.PENDING and chs[1].queued_at)
check("chapitre 2 repassé PENDING, erreur effacée",
      chs[2].status == ChapterStatus.PENDING and chs[2].error_message is None)

tasks._generate_chapter_queue_pump_impl()
check("pompe : chapitres 1 et 2 traités", len(pumped) == 2, f"{pumped}")
with Session(eng) as s:
    left = s.exec(select(Chapter).where(Chapter.queued_at.is_not(None))).all()
check("plus rien en file à la fin", not left, f"{[(c.position, c.status) for c in left]}")

with Session(eng) as s:
    bk = s.get(Book, book_id)
    bk.status = BookStatus.PROCESSING
    s.add(bk)
    s.commit()
r3 = client.post(f"/books/{book_id}/chapters/1/generate")
check("livre en cours d'analyse -> 409", r3.status_code == 409, str(r3.status_code))

print("\n[3] SEC-1/SEC-2 : garde anti cross-site et Host")
evil = client.post(f"/books/{book_id}/stop", headers={"Origin": "https://evil.example"})
check("écriture avec Origin étrangère -> 403", evil.status_code == 403, str(evil.status_code))
null = client.post(f"/books/{book_id}/stop", headers={"Origin": "null"})
check("écriture avec Origin 'null' -> 403", null.status_code == 403, str(null.status_code))
xsite = client.post(f"/books/{book_id}/stop", headers={"Sec-Fetch-Site": "cross-site"})
check("écriture Sec-Fetch-Site cross-site sans Origin -> 403", xsite.status_code == 403)
good = client.post(f"/books/{book_id}/stop", headers={"Origin": "http://localhost:3000"})
check("écriture depuis le frontend autorisé passe la garde", good.status_code != 403, str(good.status_code))
rb = client.get("/books", headers={"Host": "evil.example"})
check("Host inattendu (DNS rebinding) -> 400", rb.status_code == 400, str(rb.status_code))
check("GET normal -> 200", client.get("/books").status_code == 200)

print()
if _errors:
    print(f"{len(_errors)} échec(s)")
    sys.exit(1)
print("Tous les tests OK")
