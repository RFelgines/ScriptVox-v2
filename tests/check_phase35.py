"""check_phase35.py — Phase 35 : isolation de DATA_DIR (fix de fond, incident 2026-07-02).

Contexte : les tests écrivaient dans le vrai dossier `data/` de l'application
(chemin `Path("data")` codé en dur à 5 endroits : app/api/routes/books.py,
app/api/routes/voices.py, 3x app/workers/tasks.py) malgré des DB SQLite isolées
par test — a causé une perte réelle de couverture + audio TTS sur des livres
réels (chapitre 10 du livre 2, 83 Mo, non récupérable). Fix : `DATA_DIR` devient
un champ obligatoire de Settings (comme DATABASE_URL/HUEY_DB_PATH), et les 3
modules dérivent leur DATA_DIR depuis `get_settings().data_dir` au lieu d'un
`Path("data")` en dur.

Valide :
  - Settings() lève une ValueError explicite si DATA_DIR est absent (fail-fast,
    pas de retour silencieux vers "data").
  - Settings().data_dir reflète bien la valeur de l'env var DATA_DIR.
  - app.api.routes.books.DATA_DIR / app.api.routes.voices.DATA_DIR /
    app.workers.tasks.DATA_DIR sont tous dérivés de get_settings().data_dir
    (pas un Path("data") figé indépendant de la config).
  - Régression : les 3 usages internes de DATA_DIR dans tasks.py (chapitre,
    couverture, sample voix) utilisent bien la même constante de module (pas de
    Path("data") résiduel qui aurait survécu au refactor).

Run: .venv/Scripts/python tests/check_phase35.py
"""
import os
import re
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p35.db",
    "HUEY_DB_PATH": "./huey_test_p35.db",
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


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
from app.config import Settings, get_settings  # noqa: E402
ok("Settings, get_settings")


# ── 2. Settings().data_dir reflète DATA_DIR ───────────────────────────────────
section("Settings().data_dir == valeur de l'env var DATA_DIR")
get_settings.cache_clear()
_settings = Settings()
check("data_dir == './data_test'", _settings.data_dir == "./data_test", f"got {_settings.data_dir!r}")


# ── 3. DATA_DIR absent -> ValueError explicite (fail-fast) ───────────────────
section("Settings() sans DATA_DIR -> ValueError explicite (pas de défaut silencieux)")
_saved = os.environ.pop("DATA_DIR", None)
try:
    Settings()
    fail("Expected ValueError quand DATA_DIR est absent")
except ValueError as exc:
    check("message mentionne DATA_DIR", "DATA_DIR" in str(exc), f"got {exc}")
finally:
    if _saved is not None:
        os.environ["DATA_DIR"] = _saved
get_settings.cache_clear()


# ── 4. books.py / voices.py / tasks.py -- DATA_DIR dérivé de la config ───────
section("DATA_DIR des 3 modules dérivé de get_settings().data_dir (pas Path('data') figé)")
import app.api.routes.books as books_mod  # noqa: E402
import app.api.routes.voices as voices_mod  # noqa: E402
import app.workers.tasks as tasks_mod  # noqa: E402

_expected = Path(get_settings().data_dir)
check("books.DATA_DIR == Path(settings.data_dir)", books_mod.DATA_DIR == _expected,
      f"got {books_mod.DATA_DIR!r}")
check("voices.DATA_DIR == Path(settings.data_dir)", voices_mod.DATA_DIR == _expected,
      f"got {voices_mod.DATA_DIR!r}")
check("tasks.DATA_DIR == Path(settings.data_dir)", tasks_mod.DATA_DIR == _expected,
      f"got {tasks_mod.DATA_DIR!r}")
check("les 3 DATA_DIR ne pointent PAS vers le vrai './data' de prod",
      str(books_mod.DATA_DIR) != "data", f"got {books_mod.DATA_DIR!r}")


# ── 5. Régression : aucun Path("data")/_Path("data") littéral résiduel ───────
section("Régression : aucun Path(\"data\") codé en dur résiduel dans tasks.py/books.py/voices.py")
_hardcoded_re = re.compile(r'_?Path\(\s*["\']data["\']\s*\)')
for _mod_path in (
    ROOT / "app" / "workers" / "tasks.py",
    ROOT / "app" / "api" / "routes" / "books.py",
    ROOT / "app" / "api" / "routes" / "voices.py",
):
    _src = _mod_path.read_text(encoding="utf-8")
    _matches = _hardcoded_re.findall(_src)
    check(f"{_mod_path.name}: zéro Path(\"data\") codé en dur", len(_matches) == 0,
          f"trouvé {len(_matches)} occurrence(s)")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p35.db", "huey_test_p35.db"):
    try:
        if os.path.exists(_leftover):
            os.remove(_leftover)
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
