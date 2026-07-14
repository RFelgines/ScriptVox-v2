"""check_phase39.py — Écran Modèles : listing Piper + unload VRAM Qwen.

Valide :
  - app.schemas.models : PiperVoice, QwenStatus, ModelsResponse,
    UnloadQwenResponse s'importent proprement.
  - GET /models (happy path) : répertoire .onnx peuplé → piper non vide,
    qwen.model et qwen.device non vides, qwen.loaded est None.
  - GET /models (piper_voices_dir absent) : 200, piper: [].
  - GET /models (répertoire inexistant) : 200, piper: [].
  - POST /models/qwen/unload (happy path) : 202, status == "queued".
  - POST /models/qwen/unload (idempotent) : second appel → 202 aussi.

La tâche Huey release_qwen_vram est mockée (pas de backend SQLite Huey requis).
TTS_PROVIDER=edgetts évite les prérequis répertoire/binaire Piper au boot.

Run: .venv/Scripts/python tests/check_phase39.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",      # pas de prérequis répertoire/binaire
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p39.db",
    "HUEY_DB_PATH": "./huey_test_p39.db",
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

from app.schemas.models import (  # noqa: E402
    ModelsResponse,
    PiperVoice,
    QwenStatus,
    UnloadQwenResponse,
)

ok("PiperVoice, QwenStatus, ModelsResponse, UnloadQwenResponse")

from app.api.routes.models import router  # noqa: E402

ok("router (app.api.routes.models)")

# App de test autonome — le routeur /models sera enregistré dans
# app/main.py en Tâche 2 ; ici on le monte directement pour isoler
# la Tâche 1 de l'enregistrement global.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

_test_app = FastAPI()
_test_app.include_router(router, prefix="/models")

ok("app autonome avec /models router")


# ── 2. Schémas : valeurs et types ─────────────────────────────────────────────
section("Schémas Pydantic : construction et champs")

_v = PiperVoice(filename="fr_FR-mls-medium.onnx")
check("PiperVoice.filename", _v.filename == "fr_FR-mls-medium.onnx")

_q = QwenStatus(model="1.7b", device="cuda:0")
check("QwenStatus.model", _q.model == "1.7b")
check("QwenStatus.device", _q.device == "cuda:0")
check("QwenStatus.loaded par défaut = None", _q.loaded is None)

_r = ModelsResponse(piper=[_v], qwen=_q)
check("ModelsResponse.piper non vide", len(_r.piper) == 1)

_u = UnloadQwenResponse(status="queued", detail="ok")
check("UnloadQwenResponse.status == 'queued'", _u.status == "queued")


# ── 3. GET /models — happy path (dossier .onnx peuplé) ───────────────────────
section("GET /models — happy path : répertoire .onnx peuplé")

get_settings.cache_clear()

with tempfile.TemporaryDirectory() as _voices_dir:
    for _name in ("fr_FR-mls-medium.onnx", "en_US-ryan-high.onnx"):
        (Path(_voices_dir) / _name).touch()

    os.environ["PIPER_VOICES_DIR"] = _voices_dir
    get_settings.cache_clear()

    _client = TestClient(_test_app, raise_server_exceptions=True)
    _resp = _client.get("/models")
    check("GET /models → 200", _resp.status_code == 200, _resp.text)

    _body = _resp.json()
    check("piper est une liste", isinstance(_body.get("piper"), list))
    check("piper contient 2 voix", len(_body.get("piper", [])) == 2,
          f"got {_body.get('piper')}")
    _filenames = [v["filename"] for v in _body.get("piper", [])]
    check("piper trié alphabétiquement", _filenames == sorted(_filenames),
          f"got {_filenames}")

    _qwen = _body.get("qwen", {})
    check("qwen.model non vide", bool(_qwen.get("model")), f"got {_qwen}")
    check("qwen.device non vide", bool(_qwen.get("device")), f"got {_qwen}")
    check("qwen.loaded est null", _qwen.get("loaded") is None,
          f"got {_qwen.get('loaded')!r}")

os.environ.pop("PIPER_VOICES_DIR", None)
get_settings.cache_clear()


# ── 4. GET /models — piper_voices_dir non défini ─────────────────────────────
section("GET /models — PIPER_VOICES_DIR absent : piper: []")

# TTS_PROVIDER=edgetts : get_settings() n'exige pas PIPER_VOICES_DIR.
get_settings.cache_clear()
_client2 = TestClient(_test_app, raise_server_exceptions=True)
_resp2 = _client2.get("/models")
check("200 même sans PIPER_VOICES_DIR", _resp2.status_code == 200, _resp2.text)
check("piper: []", _resp2.json().get("piper") == [],
      f"got {_resp2.json().get('piper')}")


# ── 5. GET /models — répertoire inexistant ────────────────────────────────────
section("GET /models — répertoire inexistant : piper: []")

os.environ["PIPER_VOICES_DIR"] = "/chemin/qui/nexiste/pas"
get_settings.cache_clear()
_client3 = TestClient(_test_app, raise_server_exceptions=True)
_resp3 = _client3.get("/models")
check("200 même si répertoire inexistant", _resp3.status_code == 200, _resp3.text)
check("piper: []", _resp3.json().get("piper") == [],
      f"got {_resp3.json().get('piper')}")

os.environ.pop("PIPER_VOICES_DIR", None)
get_settings.cache_clear()


# ── 6. POST /models/qwen/unload — happy path (tâche Huey mockée) ─────────────
section("POST /models/qwen/unload — 202 + status queued (Huey mocké)")

_mock_task = MagicMock()

with patch("app.workers.tasks.release_qwen_vram", _mock_task, create=True):
    _client4 = TestClient(_test_app, raise_server_exceptions=True)
    _resp4 = _client4.post("/models/qwen/unload")
    check("POST /models/qwen/unload → 202", _resp4.status_code == 202,
          _resp4.text)
    _b4 = _resp4.json()
    check("status == 'queued'", _b4.get("status") == "queued", f"got {_b4}")
    check("detail est une chaîne non vide", bool(_b4.get("detail")), f"got {_b4}")
    check("release_qwen_vram appelée une fois", _mock_task.call_count == 1,
          f"call_count={_mock_task.call_count}")


# ── 7. POST /models/qwen/unload — idempotent ─────────────────────────────────
section("POST /models/qwen/unload — idempotent : second appel → 202")

_mock_task2 = MagicMock()

with patch("app.workers.tasks.release_qwen_vram", _mock_task2, create=True):
    _client5 = TestClient(_test_app, raise_server_exceptions=True)
    _resp5a = _client5.post("/models/qwen/unload")
    _resp5b = _client5.post("/models/qwen/unload")
    check("premier appel → 202", _resp5a.status_code == 202, _resp5a.text)
    check("second appel → 202", _resp5b.status_code == 202, _resp5b.text)
    check("release_qwen_vram appelée deux fois", _mock_task2.call_count == 2,
          f"call_count={_mock_task2.call_count}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p39.db", "huey_test_p39.db"):
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
