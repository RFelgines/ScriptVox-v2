"""check_phase15.py — Phase 14 Étape B3: QwenTTSProvider (mocks only, jamais le vrai modèle).
Run: .venv/Scripts/python tests/check_phase15.py

Décision actée (2026-06-22, mémoire tts-emotion-qwen3-direction) : B3 s'écrit et se teste
exclusivement via mocks. La vérification audio réelle (qualité FR + effet `instruct`) est
différée à une écoute manuelle par l'utilisateur — pas un test de cette suite.
"""
import array
import asyncio
import io
import os
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p15.db",
    "HUEY_DB_PATH": "./huey_test_p15.db",
    "TTS_PROVIDER": "qwen",
})
for _var in ("QWEN_MODEL", "QWEN_LANGUAGE", "QWEN_DEVICE", "QWEN_ATTN"):
    os.environ.pop(_var, None)

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
    msg = f"    FAIL  {label}" + (f" — {detail}" if detail else "")
    print(msg)
    _errors.append(msg)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        ok(label)
    else:
        fail(label, detail)


def _raises(exc_type, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
        return False
    except exc_type:
        return True
    except Exception:
        return False


# ── Section 1: config — TTS_PROVIDER=qwen accepté, défauts appliqués ─────────

section("Config: TTS_PROVIDER=qwen accepté, défauts QWEN_* appliqués")

from app.config import Settings

try:
    s = Settings()
    check("Settings() sans exception", True)
    check("tts_provider == 'qwen'", s.tts_provider == "qwen")
    check("qwen_model == '1.7b'", s.qwen_model == "1.7b")
    check("qwen_language == 'French'", s.qwen_language == "French")
    check("qwen_device == 'cuda:0'", s.qwen_device == "cuda:0")
    check("qwen_attn == 'sdpa'", s.qwen_attn == "sdpa")
except Exception as e:
    check("Settings() sans exception", False, str(e))

# ── Section 2: config — variables QWEN_* personnalisées ─────────────────────

section("Config: QWEN_MODEL/LANGUAGE/DEVICE/ATTN personnalisés stockés")

os.environ.update({
    "QWEN_MODEL": "0.6b",
    "QWEN_LANGUAGE": "English",
    "QWEN_DEVICE": "cuda:1",
    "QWEN_ATTN": "flash_attention_2",
})
try:
    s2 = Settings()
    check("qwen_model == '0.6b'", s2.qwen_model == "0.6b")
    check("qwen_language == 'English'", s2.qwen_language == "English")
    check("qwen_device == 'cuda:1'", s2.qwen_device == "cuda:1")
    check("qwen_attn == 'flash_attention_2'", s2.qwen_attn == "flash_attention_2")
finally:
    for _var in ("QWEN_MODEL", "QWEN_LANGUAGE", "QWEN_DEVICE", "QWEN_ATTN"):
        os.environ.pop(_var, None)

# ── Section 3: import paresseux — le module qwen.py ne charge PAS torch/qwen_tts ─

section("Import paresseux: app.services.tts.qwen n'importe pas torch/qwen_tts au niveau module")

import app.services.tts.qwen as qwen_mod

check("import du module sans erreur", True)
check(
    "'torch' non lié au niveau module (import différé dans _import_qwen_deps)",
    "torch" not in vars(qwen_mod),
)
check("'Qwen3TTSModel' non lié au niveau module", "Qwen3TTSModel" not in vars(qwen_mod))
check("'qwen_tts' non lié au niveau module", "qwen_tts" not in vars(qwen_mod))

from app.services.tts.qwen import (
    QwenTTSProvider,
    _float_to_pcm16,
    _resample_to_output,
    _MODEL_SAMPLE_RATE,
    _OUTPUT_SAMPLE_RATE,
    _VOICE_MAP,
)

# ── Section 4: factory -> QwenTTSProvider ────────────────────────────────────

section("Factory: get_tts_provider('qwen') -> QwenTTSProvider")

from app.services.tts.factory import get_tts_provider

mock_s = MagicMock()
mock_s.tts_provider = "qwen"
mock_s.qwen_model = "1.7b"
mock_s.qwen_language = "French"
mock_s.qwen_device = "cuda:0"
mock_s.qwen_attn = "sdpa"

provider = get_tts_provider(mock_s)
check("isinstance QwenTTSProvider", isinstance(provider, QwenTTSProvider))

# ── Section 5: _VOICE_MAP — tous les ids du catalogue résolus, presets uniques ─

section("_VOICE_MAP: tous les ids du catalogue logique résolus vers un preset Qwen unique")

from app.services.voice_assignment import NARRATOR_VOICE_ID, VOICE_CATALOGUE

all_ids: list[str] = [NARRATOR_VOICE_ID]
_seen_ids: set[str] = {NARRATOR_VOICE_ID}
for voices in VOICE_CATALOGUE.values():
    for v in voices:
        if v not in _seen_ids:
            all_ids.append(v)
            _seen_ids.add(v)

resolved_presets: list[str] = []
for vid in all_ids:
    try:
        preset = provider.resolve_voice(vid)
        check(f"'{vid}' -> preset non vide", bool(preset))
        resolved_presets.append(preset)
    except Exception as e:
        fail(f"'{vid}' résolu", str(e))

check(
    "chaque id du catalogue reçoit un preset Qwen distinct (pas de collision)",
    len(resolved_presets) == len(set(resolved_presets)),
)

# ── Section 6: voice_id inconnu -> TTSError (avant tout chargement modèle) ───

section("resolve_voice / synthesise: voice_id inconnu -> TTSError (offline, pas de modèle touché)")

from app.core.exceptions import TTSError

check(
    "resolve_voice('ghost_99') -> TTSError",
    _raises(TTSError, provider.resolve_voice, "ghost_99"),
)
check(
    "synthesise('inconnu_99') -> TTSError",
    _raises(TTSError, asyncio.run, provider.synthesise("hello", "inconnu_99")),
)

# ── Section 7: _float_to_pcm16 (stdlib pur, offline) ─────────────────────────

section("_float_to_pcm16: floats [-1, 1] -> PCM16 signé, avec clamp")

_pcm = _float_to_pcm16([0.0, 1.0, -1.0, 2.0, -2.0])
_arr = array.array("h")
_arr.frombytes(_pcm)
check("5 échantillons produits", len(_arr) == 5)
check("0.0 -> 0", _arr[0] == 0)
check("1.0 -> 32767", _arr[1] == 32767)
check("-1.0 -> -32767", _arr[2] == -32767)
check("clamp > 1.0 -> 32767", _arr[3] == 32767)
check("clamp < -1.0 -> -32767", _arr[4] == -32767)

# ── Section 8: _resample_to_output (audioop.ratecv, stdlib) ─────────────────

section("_resample_to_output: identité à 22050 Hz, réduction proportionnelle 24000->22050")

_silence_1s = b"\x00\x00" * _MODEL_SAMPLE_RATE  # 1 s de silence 16-bit @ 24000 Hz
_same = _resample_to_output(_silence_1s, _OUTPUT_SAMPLE_RATE)
check("identité si déjà 22050 Hz (no-op)", _same == _silence_1s)

_resampled = _resample_to_output(_silence_1s, _MODEL_SAMPLE_RATE)
_expected_len = len(_silence_1s) * _OUTPUT_SAMPLE_RATE // _MODEL_SAMPLE_RATE
check(
    "longueur réduite proportionnellement (24000 Hz -> 22050 Hz)",
    abs(len(_resampled) - _expected_len) <= 4,
)

# ── Section 8b: audioop absent (Python 3.13+, m10) — garde d'import ──────────
# audioop a été retiré de la stdlib en Python 3.13 (PEP 594) ; le module doit
# rester importable (audioop=None), seule une resampling réelle doit échouer,
# avec un TTSError clair au lieu d'un NameError/AttributeError opaque.

section("_resample_to_output: audioop absent + déjà 22050 Hz -> no-op, pas d'erreur")
with patch.object(qwen_mod, "audioop", None):
    _noop = _resample_to_output(_silence_1s, _OUTPUT_SAMPLE_RATE)
    check("identité préservée (aucun resampling nécessaire)", _noop == _silence_1s)

section("_resample_to_output: audioop absent + resampling requis -> TTSError clair")
with patch.object(qwen_mod, "audioop", None):
    try:
        _resample_to_output(_silence_1s, _MODEL_SAMPLE_RATE)
        check("TTSError levée quand audioop est absent et qu'un resampling est nécessaire",
              False, "aucune exception levée")
    except TTSError as exc:
        check("message mentionne audioop", "audioop" in str(exc), str(exc))
        check("message mentionne Python 3.13", "3.13" in str(exc), str(exc))
    except Exception as exc:
        check("TTSError attendue", False, f"{type(exc).__name__}: {exc}")

# ── Section 9: _ensure_model — ImportError (deps absentes) -> TTSError clair ─

section("synthesise: torch/qwen-tts absents -> TTSError mentionnant requirements-qwen.txt")


async def _call_missing_deps():
    p = QwenTTSProvider(mock_s)
    with patch.object(qwen_mod, "_import_qwen_deps", side_effect=ImportError("no torch")):
        return await p.synthesise("bonjour", "narrator")


try:
    asyncio.run(_call_missing_deps())
    check("ImportError -> TTSError", False, "aucune exception levée")
except TTSError as e:
    check("ImportError -> TTSError", True)
    check("message mentionne requirements-qwen.txt", "requirements-qwen.txt" in str(e))
except Exception as e:
    check("ImportError -> TTSError", False, f"mauvais type: {type(e).__name__}: {e}")


# ── Fakes pour les sections 10-13 (modèle Qwen jamais réellement chargé) ─────

class _FakeTorch:
    bfloat16 = "bf16-sentinel"


class _FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_custom_voice(self, **kwargs):
        self.calls.append(kwargs)
        return [[0.0] * 480], _MODEL_SAMPLE_RATE  # ~20ms de silence @ 24kHz


class _FakeModelCls:
    load_count = 0

    @classmethod
    def from_pretrained(cls, *a, **kw):
        cls.load_count += 1
        return _FakeModel()


def _fake_import_deps():
    return _FakeTorch(), _FakeModelCls


# ── Section 10: happy path — WAV valide, resamplé à 22050 Hz ─────────────────

section("synthesise: happy path (modèle mocké) -> WAV 22050 Hz mono 16-bit")


async def _call_happy(emotion=None):
    p = QwenTTSProvider(mock_s)
    with patch.object(qwen_mod, "_import_qwen_deps", side_effect=_fake_import_deps):
        wav_bytes = await p.synthesise("Bonjour tout le monde", "narrator", emotion=emotion)
    return p, wav_bytes


try:
    _provider10, _wav10 = asyncio.run(_call_happy())
    with wave.open(io.BytesIO(_wav10), "rb") as _w:
        check("WAV RIFF valide", _wav10[:4] == b"RIFF")
        check("nchannels == 1", _w.getnchannels() == 1)
        check("sampwidth == 2 (16-bit)", _w.getsampwidth() == 2)
        check(f"framerate == {_OUTPUT_SAMPLE_RATE}", _w.getframerate() == _OUTPUT_SAMPLE_RATE)
except Exception as e:
    check("happy path sans exception", False, str(e))

# ── Section 11: emotion fournie -> transmise en kwarg `instruct` ────────────

section("synthesise(..., emotion=...): transmis au modèle via le kwarg `instruct`")

try:
    _provider11, _ = asyncio.run(_call_happy(emotion="d'une voix furieuse et paniquée"))
    _last_call = _provider11._model.calls[-1]
    check("kwarg 'instruct' présent", "instruct" in _last_call)
    check(
        "valeur 'instruct' == emotion fournie",
        _last_call.get("instruct") == "d'une voix furieuse et paniquée",
    )
except Exception as e:
    check("emotion transmise", False, str(e))

# ── Section 12: emotion absente (None) -> pas de kwarg `instruct` ───────────

section("synthesise(..., emotion=None): aucun kwarg `instruct` transmis")

try:
    _provider12, _ = asyncio.run(_call_happy(emotion=None))
    _last_call12 = _provider12._model.calls[-1]
    check("kwarg 'instruct' absent", "instruct" not in _last_call12)
except Exception as e:
    check("emotion absente -> no-op", False, str(e))

# ── Section 13: modèle chargé une seule fois, réutilisé entre appels ────────

section("_ensure_model: chargé une seule fois par instance, réutilisé sur appels suivants")

_FakeModelCls.load_count = 0
try:
    p13 = QwenTTSProvider(mock_s)
    with patch.object(qwen_mod, "_import_qwen_deps", side_effect=_fake_import_deps):
        asyncio.run(p13.synthesise("Première phrase.", "male_0"))
        asyncio.run(p13.synthesise("Deuxième phrase.", "female_0"))
    check("from_pretrained appelé une seule fois pour 2 synthèses", _FakeModelCls.load_count == 1)
except Exception as e:
    check("modèle réutilisé", False, str(e))

# ── Rapport ───────────────────────────────────────────────────────────────────

print(f"\n{'='*52}")
if _errors:
    print(f"FAIL — {len(_errors)} erreur(s) :")
    for e in _errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"OK — Toutes les sections passent (B3: QwenTTSProvider, mocks only).")
