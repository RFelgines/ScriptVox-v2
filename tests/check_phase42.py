"""check_phase42.py — Phase 42 : commutation à chaud du provider LLM.

Contexte : le provider LLM était figé au démarrage via Settings.llm_provider
(lru_cache). Cette phase ajoute AppSetting.preferred_llm_provider, consultée
à chaque run par _effective_llm_provider, de sorte que l'UI Paramètres peut
basculer entre "ollama" et "gemini" sans redémarrer l'application.

Valide :
  - VALID_LLM_PROVIDERS == {"gemini", "ollama"} (export public de config.py).
  - AppSetting.preferred_llm_provider est nullable et persistable.
  - _effective_llm_provider : None si pas de préférence ; sinon la valeur en DB.
  - get_llm_provider(settings, override=...) : override prime sur settings.llm_provider
    (même comportement que get_tts_provider avec son paramètre override).
  - GET /settings expose default_llm_provider, preferred_llm_provider (None),
    available_llm_providers (["gemini", "ollama"]).
  - PATCH /settings avec preferred_llm_provider="ollama" -> 200, persisté.
  - PATCH /settings avec preferred_llm_provider="openai" -> 422 (valeur inconnue).

Run: python tests/check_phase42.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "piper",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p39.db",
    "HUEY_DB_PATH": "./huey_test_p39.db",
    "DATA_DIR": "./data_test",
    "PIPER_VOICES_DIR": "./voices",
    "PIPER_BINARY_PATH": sys.executable,
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

from app.config import VALID_LLM_PROVIDERS, get_settings  # noqa: E402
from app.models import AppSetting  # noqa: E402
from app.services.llm.factory import get_llm_provider  # noqa: E402
from app.services.llm.gemini import GeminiProvider  # noqa: E402
from app.services.llm.ollama import OllamaProvider  # noqa: E402
from app.workers.tasks import _effective_llm_provider  # noqa: E402

ok("VALID_LLM_PROVIDERS, AppSetting, get_llm_provider(override=...), _effective_llm_provider")

get_settings.cache_clear()


def _make_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


# ── 2. VALID_LLM_PROVIDERS ───────────────────────────────────────────────────
section("VALID_LLM_PROVIDERS == {'gemini', 'ollama'}")
check("valeurs attendues", VALID_LLM_PROVIDERS == frozenset({"gemini", "ollama"}),
      f"got {VALID_LLM_PROVIDERS}")


# ── 3. AppSetting.preferred_llm_provider est nullable ────────────────────────
section("AppSetting.preferred_llm_provider : champ nullable, persistable")
_e3 = _make_engine()
with Session(_e3) as s:
    row = AppSetting(id=1)
    s.add(row)
    s.commit()
    s.refresh(row)
    check("par défaut None", row.preferred_llm_provider is None,
          f"got {row.preferred_llm_provider!r}")

    row.preferred_llm_provider = "gemini"
    s.add(row)
    s.commit()
    s.refresh(row)
    check("persisté 'gemini'", row.preferred_llm_provider == "gemini",
          f"got {row.preferred_llm_provider!r}")

    row.preferred_llm_provider = None
    s.add(row)
    s.commit()
    s.refresh(row)
    check("remis à None", row.preferred_llm_provider is None,
          f"got {row.preferred_llm_provider!r}")


# ── 4. _effective_llm_provider : ordre de priorité ──────────────────────────
section("_effective_llm_provider : DB vide -> None ; préférence définie -> retournée")
_e4 = _make_engine()
with Session(_e4) as s:
    check("DB vide -> None",
          _effective_llm_provider(s) is None)

    s.add(AppSetting(id=1, preferred_llm_provider="gemini"))
    s.commit()
    check("preferred_llm_provider='gemini' -> 'gemini'",
          _effective_llm_provider(s) == "gemini")

_e4b = _make_engine()
with Session(_e4b) as s:
    s.add(AppSetting(id=1, preferred_llm_provider="ollama"))
    s.commit()
    check("preferred_llm_provider='ollama' -> 'ollama'",
          _effective_llm_provider(s) == "ollama")

_e4c = _make_engine()
with Session(_e4c) as s:
    s.add(AppSetting(id=1))  # preferred_llm_provider non défini (None)
    s.commit()
    check("AppSetting présent mais preferred_llm_provider=None -> None",
          _effective_llm_provider(s) is None)


# ── 5. get_llm_provider(settings, override=...) ──────────────────────────────
section("get_llm_provider : override prime sur settings.llm_provider")

get_settings.cache_clear()
settings = get_settings()  # LLM_PROVIDER=ollama

# Happy path : pas d'override => respecte settings.llm_provider
provider_no_override = get_llm_provider(settings, override=None)
check("override=None + LLM_PROVIDER=ollama -> OllamaProvider",
      isinstance(provider_no_override, OllamaProvider),
      f"got {type(provider_no_override).__name__}")

# Override gemini => GeminiProvider même si .env dit ollama
os.environ["GEMINI_API_KEY"] = "fake-key-for-type-check"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"
get_settings.cache_clear()
settings_with_gemini_creds = get_settings()

# Remettre LLM_PROVIDER=ollama pour simuler l'override depuis AppSetting
os.environ["LLM_PROVIDER"] = "ollama"
get_settings.cache_clear()
settings_ollama = get_settings()

provider_override_gemini = get_llm_provider(settings_with_gemini_creds, override="gemini")
check("override='gemini' -> GeminiProvider",
      isinstance(provider_override_gemini, GeminiProvider),
      f"got {type(provider_override_gemini).__name__}")

provider_override_ollama = get_llm_provider(settings_ollama, override="ollama")
check("override='ollama' -> OllamaProvider",
      isinstance(provider_override_ollama, OllamaProvider),
      f"got {type(provider_override_ollama).__name__}")

# Nettoyage
del os.environ["GEMINI_API_KEY"]
del os.environ["GEMINI_MODEL"]
get_settings.cache_clear()


# ── 6. GET /settings expose les champs LLM ──────────────────────────────────
section("GET /settings : default_llm_provider + preferred_llm_provider + available_llm_providers")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

_e6 = _make_engine()


def _override_session():
    with Session(_e6) as s:
        yield s


app.dependency_overrides[get_session] = _override_session
_client = TestClient(app)

_resp = _client.get("/settings")
check("GET /settings -> 200", _resp.status_code == 200, _resp.text)
_body = _resp.json()
check("default_llm_provider présent", "default_llm_provider" in _body, str(_body.keys()))
check("default_llm_provider == 'ollama'", _body.get("default_llm_provider") == "ollama",
      f"got {_body.get('default_llm_provider')!r}")
check("preferred_llm_provider par défaut -> None",
      _body.get("preferred_llm_provider") is None,
      f"got {_body.get('preferred_llm_provider')!r}")
check("available_llm_providers == ['gemini', 'ollama']",
      set(_body.get("available_llm_providers", [])) == {"gemini", "ollama"},
      f"got {_body.get('available_llm_providers')}")


# ── 7. PATCH /settings : persistance et validation ─────────────────────────
section("PATCH /settings : preferred_llm_provider persisté ; valeur invalide -> 422")

_resp_patch = _client.patch("/settings", json={"preferred_llm_provider": "ollama"})
check("PATCH preferred_llm_provider='ollama' -> 200",
      _resp_patch.status_code == 200, _resp_patch.text)
check("preferred_llm_provider persisté 'ollama'",
      _resp_patch.json().get("preferred_llm_provider") == "ollama",
      f"got {_resp_patch.json().get('preferred_llm_provider')!r}")

_resp_reset = _client.patch("/settings", json={"preferred_llm_provider": None})
check("PATCH preferred_llm_provider=None -> 200 (reset)",
      _resp_reset.status_code == 200, _resp_reset.text)
check("preferred_llm_provider reset -> None",
      _resp_reset.json().get("preferred_llm_provider") is None,
      f"got {_resp_reset.json().get('preferred_llm_provider')!r}")

_resp_bad = _client.patch("/settings", json={"preferred_llm_provider": "openai"})
check("PATCH preferred_llm_provider='openai' (inconnu) -> 422",
      _resp_bad.status_code == 422, _resp_bad.text)

app.dependency_overrides.pop(get_session, None)


# ── Nettoyage ────────────────────────────────────────────────────────────────
for _leftover in ("scriptvox_test_p39.db", "huey_test_p39.db"):
    try:
        if os.path.exists(_leftover):
            os.remove(_leftover)
    except PermissionError:
        pass


# ── Résumé ───────────────────────────────────────────────────────────────────
print(f"\n{'='*52}")
if _errors:
    print(f"{FAIL} {len(_errors)} erreur(s) :")
    for e in _errors:
        print(e)
    sys.exit(1)
else:
    print(f"{PASS} {_n}/{_n} sections OK")
