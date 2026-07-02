"""check_phase31.py — Phase 31 (Lot F1, audit 2026-07-02) : génération de sample
de voix clonée hors du process API (M5).

Avant ce lot, POST /voices/{id}/sample chargeait le checkpoint Qwen et tenait
l'état CUDA **dans le process FastAPI lui-même** (`_generate_voice_sample_async`),
au risque d'entrer en collision avec un Huey worker qui aurait déjà un modèle
Qwen chargé pour une génération de livre en cours — deux process distincts sur
le même GPU sans coordination. La tâche Huey `generate_voice_sample` existait
déjà mais n'était jamais dispatchée (code mort) ; la route bascule maintenant
dessus.

Valide :
  - `_generate_voice_sample_async` n'existe plus (dead code supprimé).
  - POST /voices/{id}/sample sur une voix CLONED -> 202 (pas 200), dispatch
    `generate_voice_sample(voice_id)` au lieu de générer en ligne.
  - Régressions inchangées : voix inconnue -> 404 ; voix non-CLONED -> 400.
  - `_generate_voice_sample_impl` : libère la VRAM Qwen via `_release_qwen_gpu`
    après un run réussi ET après un run en échec (jusqu'ici cette fonction ne
    libérait jamais rien -- seule l'ancienne route async le faisait).
  - `_generate_voice_sample_impl` : no-op propre si TTS_PROVIDER != qwen.

Run: .venv/Scripts/python tests/check_phase31.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p31.db",
    "HUEY_DB_PATH": "./huey_test_p31.db",
    "DATA_DIR": "./data_test",
    "EDGETTS_LOCALE": "fr-FR",
})

_n = 0


def section(title: str) -> None:
    global _n
    _n += 1
    print(f"\n[{_n}] {title}")


def ok(msg: str) -> None:
    print(f"    ok  {msg}")


def die(msg: str) -> None:
    print(f"  FAIL  {msg}")
    sys.exit(1)


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
import app.workers.tasks as tasks_mod  # noqa: E402
from app.workers.tasks import _generate_voice_sample_impl, generate_voice_sample  # noqa: E402
ok("app.workers.tasks, _generate_voice_sample_impl, generate_voice_sample")


# ── 2. Dead code retiré ────────────────────────────────────────────────────────
section("_generate_voice_sample_async n'existe plus (supprimé, dead code)")
if hasattr(tasks_mod, "_generate_voice_sample_async"):
    die("_generate_voice_sample_async devrait avoir été supprimé")
ok("_generate_voice_sample_async absent du module")


# ── 3. API — setup TestClient ─────────────────────────────────────────────────
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.core.enums import VoiceKind, Gender  # noqa: E402
from app.models.entities import Voice  # noqa: E402

_engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine)


def _session_override():
    with Session(_engine) as s:
        yield s


app.dependency_overrides[get_session] = _session_override

with Session(_engine) as s:
    s.add(Voice(
        voice_id="patrick-baud", name="Patrick Baud", kind=VoiceKind.CLONED,
        gender=Gender.MALE, reference_audio_path="/data/voices/patrick-baud/ref.wav",
    ))
    s.add(Voice(voice_id="male_0", name="Male 0", kind=VoiceKind.CATALOGUE))
    s.commit()


# ── 4. POST /voices/{id}/sample sur une voix CLONED -> 202 + dispatch Huey ────
section("POST /voices/{id}/sample -- voix CLONED -> 202, dispatch generate_voice_sample")
with patch.object(tasks_mod, "generate_voice_sample") as _mock_task:
    with TestClient(app, raise_server_exceptions=False) as tc:
        r = tc.post("/voices/patrick-baud/sample")
if r.status_code != 202:
    die(f"Expected 202, got {r.status_code}: {r.text}")
if _mock_task.call_count != 1:
    die(f"Expected generate_voice_sample called once, got {_mock_task.call_count}")
if _mock_task.call_args.args != ("patrick-baud",):
    die(f"Expected dispatched with ('patrick-baud',), got {_mock_task.call_args}")
ok("202 + generate_voice_sample('patrick-baud') dispatché une fois")


# ── 5. La réponse ne bloque pas sur la génération (pas de génération inline) ──
section("La route ne génère plus rien elle-même (pas d'appel QwenTTSProvider)")
with patch.object(tasks_mod, "generate_voice_sample") as _mock_task5, \
     patch("app.services.tts.qwen.QwenTTSProvider") as _mock_qwen5:
    with TestClient(app, raise_server_exceptions=False) as tc:
        tc.post("/voices/patrick-baud/sample")
if _mock_qwen5.called:
    die("QwenTTSProvider ne devrait jamais être instancié dans le process API")
ok("Aucune instanciation de QwenTTSProvider dans le process API")


# ── 6. Régression : voix inconnue -> 404 ──────────────────────────────────────
section("POST /voices/{id}/sample -- voix inconnue -> 404 (inchangé)")
with patch.object(tasks_mod, "generate_voice_sample") as _mock_task6:
    with TestClient(app, raise_server_exceptions=False) as tc:
        r6 = tc.post("/voices/does-not-exist/sample")
if r6.status_code != 404:
    die(f"Expected 404, got {r6.status_code}: {r6.text}")
if _mock_task6.called:
    die("generate_voice_sample ne devrait pas être dispatché pour une voix inconnue")
ok("404 + aucun dispatch")


# ── 7. Régression : voix non-CLONED -> 400 ────────────────────────────────────
section("POST /voices/{id}/sample -- voix CATALOGUE -> 400 (inchangé)")
with patch.object(tasks_mod, "generate_voice_sample") as _mock_task7:
    with TestClient(app, raise_server_exceptions=False) as tc:
        r7 = tc.post("/voices/male_0/sample")
if r7.status_code != 400:
    die(f"Expected 400, got {r7.status_code}: {r7.text}")
if _mock_task7.called:
    die("generate_voice_sample ne devrait pas être dispatché pour une voix non-CLONED")
ok("400 + aucun dispatch")


# _generate_voice_sample_impl builds its output path from app.workers.tasks.DATA_DIR
# (derived from get_settings().data_dir, isolated to ./data_test for tests since
# Phase 35 -- incident 2026-07-02, real data/ was getting written by tests).
from app.config import get_settings as _real_get_settings  # noqa: E402

_TEST_SAMPLE_PATH = ROOT / _real_get_settings().data_dir / "voice_samples" / "qwen_patrick-baud.wav"


def _cleanup_test_sample() -> None:
    try:
        if _TEST_SAMPLE_PATH.exists():
            _TEST_SAMPLE_PATH.unlink()
    except OSError:
        pass


# ── 8. _generate_voice_sample_impl -- no-op si TTS_PROVIDER != qwen ──────────
section("_generate_voice_sample_impl -- no-op propre si TTS_PROVIDER != qwen (edgetts)")
with patch("app.services.tts.qwen.QwenTTSProvider") as _mock_qwen8:
    _generate_voice_sample_impl("patrick-baud")
if _mock_qwen8.called:
    die("QwenTTSProvider ne devrait pas être instancié quand TTS_PROVIDER != qwen")
ok("no-op confirmé, aucun modèle chargé")


# ── 9. _generate_voice_sample_impl -- succès : fichier écrit + VRAM libérée ──
section("_generate_voice_sample_impl -- succès : sample écrit + _release_qwen_gpu appelé")


class _FakeProvider9:
    def __init__(self, settings):
        self._model = "loaded-model"
        self._base_model = "loaded-base"

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        return b"RIFF....WAVEfake"


os.environ["TTS_PROVIDER"] = "qwen"
_real_get_settings.cache_clear()
try:
    with patch("app.services.tts.qwen.QwenTTSProvider", _FakeProvider9), \
         patch("app.workers.tasks._release_qwen_gpu") as _mock_release9, \
         patch("app.core.db.get_engine", return_value=_engine):
        _generate_voice_sample_impl("patrick-baud")

    if not _TEST_SAMPLE_PATH.exists():
        die(f"Sample WAV not written at {_TEST_SAMPLE_PATH}")
    if _mock_release9.call_count != 1:
        die(f"Expected _release_qwen_gpu called once, got {_mock_release9.call_count}")
    ok("sample écrit sur disque + VRAM Qwen libérée après succès")
finally:
    _cleanup_test_sample()
    os.environ["TTS_PROVIDER"] = "edgetts"
    _real_get_settings.cache_clear()


# ── 10. _generate_voice_sample_impl -- échec TTS : VRAM quand même libérée ───
section("_generate_voice_sample_impl -- échec synthesise() : _release_qwen_gpu appelé quand même")


class _FailingProvider10:
    def __init__(self, settings):
        self._model = "loaded-model"
        self._base_model = None

    async def synthesise(self, *a, **kw):
        raise RuntimeError("GPU OOM simulé")


os.environ["TTS_PROVIDER"] = "qwen"
_real_get_settings.cache_clear()
try:
    with patch("app.services.tts.qwen.QwenTTSProvider", _FailingProvider10), \
         patch("app.workers.tasks._release_qwen_gpu") as _mock_release10, \
         patch("app.core.db.get_engine", return_value=_engine):
        try:
            _generate_voice_sample_impl("patrick-baud")
        except Exception as exc:
            die(f"_generate_voice_sample_impl ne devrait jamais laisser fuiter une exception: {exc}")

    if _mock_release10.call_count != 1:
        die(f"Expected _release_qwen_gpu called once even on failure, got {_mock_release10.call_count}")
    ok("exception avalée (loggée) + VRAM libérée malgré l'échec")
finally:
    _cleanup_test_sample()
    os.environ["TTS_PROVIDER"] = "edgetts"
    _real_get_settings.cache_clear()


# ── Nettoyage ─────────────────────────────────────────────────────────────────
app.dependency_overrides.clear()
_cleanup_test_sample()
for leftover in ("scriptvox_test_p31.db", "huey_test_p31.db"):
    try:
        if os.path.exists(leftover):
            os.remove(leftover)
    except PermissionError:
        pass

print(f"\n{'='*52}")
print(f"\033[32mOK\033[0m {_n}/{_n} sections passées")
