"""check_phase38.py — Phase 38 : langue de préférence (repli de détection).

Contexte : le sélecteur de langue en haut de l'écran (Nav/LanguageContext) ne
pilote que l'affichage de l'UI. Ce chantier ajoute un réglage distinct en
Paramètres, AppSetting.preferred_language, consulté uniquement quand la
langue d'un livre n'a pas pu être détectée (dc:language EPUB absent/non
reconnu) ET qu'aucune langue n'est déjà connue pour ce livre (première
ingestion, sans override manuel préexistant). Zéro impact sur les livres déjà
correctement détectés ou déjà édités manuellement.

Valide :
  - _effective_book_language : dc:language détecté > langue déjà connue >
    préférence globale > None (résolution complète des 4 priorités).
  - GET /settings expose preferred_language + available_languages ("en","fr").
  - PATCH /settings valide et persiste preferred_language ; rejette une valeur
    hors AVAILABLE_LANGUAGES (422).
  - AVAILABLE_LANGUAGES (language_profiles.py) reste alignée sur les profils
    réellement enregistrés (fr, en) -- pas de liste dupliquée à la main.

Run: .venv/Scripts/python tests/check_phase38.py
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p38.db",
    "HUEY_DB_PATH": "./huey_test_p38.db",
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
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.models import AppSetting  # noqa: E402
from app.services.llm.language_profiles import AVAILABLE_LANGUAGES  # noqa: E402
from app.workers.tasks import _effective_book_language  # noqa: E402
ok("_effective_book_language, AppSetting, AVAILABLE_LANGUAGES")

get_settings.cache_clear()


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


# ── 2. AVAILABLE_LANGUAGES reflète les profils enregistrés ──────────────────
section("AVAILABLE_LANGUAGES == {'fr', 'en'}")
check("codes attendus", set(AVAILABLE_LANGUAGES) == {"fr", "en"}, f"got {AVAILABLE_LANGUAGES}")


# ── 3. _effective_book_language : ordre de priorité complet ─────────────────
section("_effective_book_language : dc:language > langue connue > préférence globale > None")

_e3 = _make_test_engine()
with Session(_e3) as _sess:
    check("rien nulle part -> None",
          _effective_book_language(None, None, _sess) is None)

    _sess.add(AppSetting(id=1, preferred_language="en"))
    _sess.commit()
    check("pas de parsed.language, pas de langue connue, préférence globale='en' -> 'en'",
          _effective_book_language(None, None, _sess) == "en")
    check("langue déjà connue='fr' prime sur la préférence globale",
          _effective_book_language(None, "fr", _sess) == "fr")
    check("dc:language détecté='en-US' prime sur tout le reste",
          _effective_book_language("en-US", "fr", _sess) == "en-US")


# ── 4. GET/PATCH /settings exposent et valident preferred_language ──────────
section("GET/PATCH /settings : preferred_language + available_languages")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

_e4 = _make_test_engine()


def _override_get_session():
    with Session(_e4) as s:
        yield s


app.dependency_overrides[get_session] = _override_get_session
_client = TestClient(app)

_resp_get = _client.get("/settings")
check("GET /settings -> 200", _resp_get.status_code == 200, _resp_get.text)
_body = _resp_get.json()
check("available_languages contient fr et en",
      set(_body.get("available_languages", [])) == {"fr", "en"}, f"got {_body}")
check("preferred_language par défaut -> None", _body.get("preferred_language") is None)

_resp_patch = _client.patch("/settings", json={"preferred_language": "en"})
check("PATCH /settings preferred_language='en' -> 200", _resp_patch.status_code == 200, _resp_patch.text)
check("preferred_language persisté", _resp_patch.json().get("preferred_language") == "en")

_resp_bad = _client.patch("/settings", json={"preferred_language": "de"})
check("PATCH /settings preferred_language='de' (non supporté) -> 422",
      _resp_bad.status_code == 422, _resp_bad.text)

app.dependency_overrides.pop(get_session, None)


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p38.db", "huey_test_p38.db"):
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
