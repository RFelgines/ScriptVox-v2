"""check_phase25.py — Phase 25 (Lot D, audit 2026-07-02) : suppression d'ElevenLabs.

ElevenLabs n'a jamais pu fonctionner (audit finding M2) : les voice_id logiques du
catalogue (male_0…) étaient injectés tels quels dans l'URL de l'API ElevenLabs (qui
attend un UUID de voix — aucun mapping n'existait), et le modèle codé en dur était
anglais-only. Décision (2026-07-02, option KISS) : retirer complètement le provider.

Valide :
  - "elevenlabs" n'est plus une valeur acceptée (Settings, VALID_TTS_PROVIDERS).
  - Le module app/services/tts/elevenlabs.py n'existe plus.
  - Le factory ne retombe plus silencieusement sur Piper pour une valeur inconnue
    (bug latent découvert en préparant ce lot : un book.tts_provider="elevenlabs"
    stocké avant cette migration doit lever une erreur claire, pas être resynthétisé
    avec la mauvaise voix sans avertissement).
  - piper / edgetts / qwen restent inchangés (régression).
  - PATCH /books rejette désormais "elevenlabs" (422).
  - GET /settings n'annonce plus "elevenlabs" dans available_tts_providers.

Run: .venv/Scripts/python tests/check_phase25.py
"""
import os
import sys
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p25.db",
    "HUEY_DB_PATH": "./huey_test_p25.db",
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
section("Modules TTS s'importent proprement")
from app.config import VALID_TTS_PROVIDERS, get_settings  # noqa: E402
from app.services.tts.edgetts import EdgeTTSProvider  # noqa: E402
from app.services.tts.factory import get_tts_provider  # noqa: E402
from app.services.tts.piper import PiperProvider  # noqa: E402
from app.services.tts.qwen import QwenTTSProvider  # noqa: E402
ok("config, edgetts, piper, qwen, factory")


# ── 2. "elevenlabs" retiré de VALID_TTS_PROVIDERS ─────────────────────────────
section("VALID_TTS_PROVIDERS ne contient plus 'elevenlabs'")
check("elevenlabs absent", "elevenlabs" not in VALID_TTS_PROVIDERS, f"got {sorted(VALID_TTS_PROVIDERS)}")
check("piper/edgetts/qwen toujours présents",
      {"piper", "edgetts", "qwen"} <= VALID_TTS_PROVIDERS, f"got {sorted(VALID_TTS_PROVIDERS)}")


# ── 3. Settings(TTS_PROVIDER=elevenlabs) -> ValueError (choix invalide) ──────
section("Settings(TTS_PROVIDER=elevenlabs) lève ValueError (valeur non acceptée)")
os.environ["TTS_PROVIDER"] = "elevenlabs"
get_settings.cache_clear()
try:
    get_settings()
    fail("Expected ValueError pour TTS_PROVIDER=elevenlabs")
except ValueError as exc:
    check("message mentionne 'Invalid TTS_PROVIDER'", "Invalid TTS_PROVIDER" in str(exc), str(exc))
os.environ["TTS_PROVIDER"] = "edgetts"
get_settings.cache_clear()


# ── 4. Le module elevenlabs.py n'existe plus ──────────────────────────────────
section("app/services/tts/elevenlabs.py a été supprimé")
_elevenlabs_module = ROOT / "app" / "services" / "tts" / "elevenlabs.py"
check("fichier absent du disque", not _elevenlabs_module.exists(), str(_elevenlabs_module))
try:
    import app.services.tts.elevenlabs  # noqa: F401
    fail("Expected ModuleNotFoundError en important app.services.tts.elevenlabs")
except ModuleNotFoundError:
    ok("ModuleNotFoundError levée à l'import, comme attendu")


# ── 5. Factory : override='elevenlabs' périmé -> erreur claire (pas de repli
#      silencieux sur Piper) ──────────────────────────────────────────────────
section("get_tts_provider(override='elevenlabs') lève une erreur explicite (pas un repli silencieux)")
get_settings.cache_clear()
_settings5 = get_settings()
try:
    _result5 = get_tts_provider(_settings5, override="elevenlabs")
    fail(
        "Aucune exception levée -- repli silencieux détecté",
        f"got {type(_result5).__name__} (bug latent : un book.tts_provider='elevenlabs' "
        "stocké avant cette migration serait resynthétisé avec la mauvaise voix, sans erreur)",
    )
except ValueError as exc:
    check("ValueError mentionne le provider inconnu", "elevenlabs" in str(exc), str(exc))


# ── 6-8. Régression : piper / edgetts / qwen toujours corrects ───────────────
section("Régression: get_tts_provider() toujours correct pour piper / edgetts / qwen")
_p6 = get_tts_provider(_settings5, override="piper")
check("override='piper' -> PiperProvider", isinstance(_p6, PiperProvider), type(_p6).__name__)

_p7 = get_tts_provider(_settings5, override="edgetts")
check("override='edgetts' -> EdgeTTSProvider", isinstance(_p7, EdgeTTSProvider), type(_p7).__name__)

_p8 = get_tts_provider(_settings5, override="qwen")
check("override='qwen' -> QwenTTSProvider", isinstance(_p8, QwenTTSProvider), type(_p8).__name__)

_p9 = get_tts_provider(_settings5)  # pas d'override -> provider global (edgetts ici)
check("sans override -> provider global (edgetts)", isinstance(_p9, EdgeTTSProvider), type(_p9).__name__)


# ── 9. Intégration API : PATCH /books rejette 'elevenlabs' (422) ─────────────
section("PATCH /books/{id}: tts_provider='elevenlabs' -> 422 (n'est plus accepté)")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.core.db as db_module  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Book  # noqa: E402

_e9 = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_e9)


def _session9():
    with Session(_e9) as s:
        yield s


with Session(_e9) as _s:
    _b9 = Book(title="ElevenLabsRejected", source_path="/tmp/x.epub")
    _s.add(_b9)
    _s.commit()
    _s.refresh(_b9)
    _b9_id = _b9.id

app.dependency_overrides[get_session] = _session9
with patch("app.core.db.get_engine", return_value=_e9):
    with TestClient(app, raise_server_exceptions=False) as _tc:
        _r9 = _tc.patch(f"/books/{_b9_id}", json={"tts_provider": "elevenlabs"})
        check("422 attendu", _r9.status_code == 422, f"got {_r9.status_code} ({_r9.text})")

        _r9b = _tc.get("/settings")
        check(
            "GET /settings: available_tts_providers ne contient plus 'elevenlabs'",
            "elevenlabs" not in _r9b.json().get("available_tts_providers", []),
            f"got {_r9b.json()}",
        )
app.dependency_overrides.clear()


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p25.db", "huey_test_p25.db"):
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
