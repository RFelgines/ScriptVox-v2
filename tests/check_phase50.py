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


print()
if _errors:
    print(f"ÉCHEC : {len(_errors)} vérification(s)")
    sys.exit(1)
print("OK : toutes les vérifications passent")
