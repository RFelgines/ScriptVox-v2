"""check_phase12.py — Phase 11 Etape 1a : CORS backend.

Verifie :
  - Settings.frontend_origins : valeur par defaut et parsing multi-origines.
  - CORSMiddleware : header Access-Control-Allow-Origin present pour une origine
    autorisee, absent pour une origine non autorisee.

Run: .venv/Scripts/python tests/check_phase12.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p12.db",
    "HUEY_DB_PATH": "./huey_test_p12.db",
    "TTS_PROVIDER": "edgetts",
    # FRONTEND_ORIGINS absent au depart (tests de parsing)
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


# ── 1. frontend_origins -- valeur par defaut (FRONTEND_ORIGINS absent) ────────
section("Settings.frontend_origins -- defaut = ['http://localhost:3000']")
from app.config import Settings  # noqa: E402

_saved = os.environ.pop("FRONTEND_ORIGINS", None)
try:
    s = Settings()
    check(
        "frontend_origins == ['http://localhost:3000']",
        s.frontend_origins == ["http://localhost:3000"],
        str(s.frontend_origins),
    )
finally:
    if _saved is not None:
        os.environ["FRONTEND_ORIGINS"] = _saved


# ── 2. frontend_origins -- parsing multi-origines avec espaces et virgule trailing
section("Settings.frontend_origins -- parsing 'http://a.com, http://b.com ,'")
os.environ["FRONTEND_ORIGINS"] = "http://a.com, http://b.com ,"
s2 = Settings()
check(
    "parse 2 origines, strip espaces, ignore virgule trailing",
    s2.frontend_origins == ["http://a.com", "http://b.com"],
    str(s2.frontend_origins),
)


# ── 3. CORS happy path -- Origin autorisee => header present ──────────────────
section("CORS -- Origin: http://localhost:3000 => Access-Control-Allow-Origin present")

os.environ["FRONTEND_ORIGINS"] = "http://localhost:3000"

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()  # recharge Settings avec FRONTEND_ORIGINS courant

from app.main import app  # noqa: E402  (appelle get_settings() → CORSMiddleware cable)
from fastapi.testclient import TestClient  # noqa: E402

# Context manager obligatoire : déclenche le lifespan (init_db -> tables créées
# + voix seedées). Sans lui, GET /voices (lecture en base depuis le seed Voice,
# voir [[ui_ux_plan]] Phase 3a) plante avec "no such table" -- /voices n'a plus
# zéro dépendance DB comme avant cette phase.
with TestClient(app, raise_server_exceptions=False) as client:
    resp = client.get("/voices", headers={"Origin": "http://localhost:3000"})
    acao = resp.headers.get("access-control-allow-origin", "")
    check("reponse HTTP 2xx ou autre (pas d'erreur reseau)", resp.status_code < 500, str(resp.status_code))
    check(
        "Access-Control-Allow-Origin = http://localhost:3000",
        acao == "http://localhost:3000",
        f"got: {acao!r}",
    )

    # ── 4. CORS failure -- Origin non autorisee => header absent ──────────────
    section("CORS -- Origin: http://evil.com => Access-Control-Allow-Origin absent")

    resp2 = client.get("/voices", headers={"Origin": "http://evil.com"})
    acao2 = resp2.headers.get("access-control-allow-origin", "")
    check(
        "Access-Control-Allow-Origin absent pour origine non autorisee",
        acao2 != "http://evil.com",
        f"got: {acao2!r}",
    )


# ── Resume ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
