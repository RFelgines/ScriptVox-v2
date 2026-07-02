"""Phase 18 Étape 1 — contrat Voice dynamique : VoiceCreate, VoiceResponse.has_reference_audio,
BaseTTSProvider.synthesise(…, reference_audio_path=None).
Run: .venv/Scripts/python tests/check_phase17.py
"""
import inspect
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p17.db",
    "HUEY_DB_PATH": "./huey_test_p17.db",
    "DATA_DIR": "./data_test",
    "PIPER_VOICES_DIR": "./voices",
    "PIPER_BINARY_PATH": sys.executable,
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


# ── 1. Imports ────────────────────────────────────────────────────────────────
section("Phase 18 Étape 1 modules import cleanly")

import pydantic  # noqa: E402
from app.core.enums import Gender, VoiceKind  # noqa: E402
from app.schemas.voice import VoiceCreate, VoiceResponse  # noqa: E402
from app.services.tts.base import BaseTTSProvider  # noqa: E402

ok("VoiceCreate, VoiceResponse, BaseTTSProvider")


# ── 2. VoiceCreate — champs requis/optionnels ─────────────────────────────────
section("VoiceCreate — name requis, gender optionnel")

vc1 = VoiceCreate(name="Axolot")
assert vc1.name == "Axolot"
assert vc1.gender is None
ok("VoiceCreate(name=...) -- gender absent -> None")

vc2 = VoiceCreate(name="Macron", gender=Gender.MALE)
assert vc2.gender == Gender.MALE
ok("VoiceCreate(name=..., gender=MALE)")


# ── 3. VoiceCreate — name manquant → ValidationError ────────────────────────
section("VoiceCreate — name manquant lève ValidationError")

try:
    VoiceCreate()  # type: ignore[call-arg]
    die("Devrait lever ValidationError quand name est absent")
except pydantic.ValidationError:
    ok("ValidationError levée comme attendu")


# ── 4. VoiceResponse — has_reference_audio défaut False ──────────────────────
section("VoiceResponse — has_reference_audio défaut False")

vr = VoiceResponse(id="male_0", name="Henri", kind=VoiceKind.CATALOGUE)
assert hasattr(vr, "has_reference_audio"), "Le champ has_reference_audio est absent de VoiceResponse"
assert vr.has_reference_audio is False
ok("has_reference_audio = False par défaut")


# ── 5. VoiceResponse — has_reference_audio peut être True ────────────────────
section("VoiceResponse — has_reference_audio=True accepté")

vr2 = VoiceResponse(
    id="cloned_0", name="Axolot", kind=VoiceKind.CLONED,
    has_reference_audio=True,
)
assert vr2.has_reference_audio is True
ok("has_reference_audio=True OK")


# ── 6. VoiceResponse — model_config from_attributes préservé ─────────────────
section("VoiceResponse.model_config — from_attributes toujours actif")

cfg = VoiceResponse.model_config
assert cfg.get("from_attributes") is True, "from_attributes supprimé accidentellement"
ok("from_attributes=True préservé")


# ── 7. BaseTTSProvider.synthesise — signature contient reference_audio_path ──
section("BaseTTSProvider.synthesise — reference_audio_path présent dans la signature")

sig = inspect.signature(BaseTTSProvider.synthesise)
params = sig.parameters
assert "reference_audio_path" in params, (
    f"Le paramètre reference_audio_path est absent de BaseTTSProvider.synthesise. "
    f"Paramètres actuels : {list(params)}"
)
p = params["reference_audio_path"]
assert p.default is None, f"reference_audio_path doit défaut à None, obtenu : {p.default!r}"
ok("reference_audio_path: str | None = None présent")


# ── 8. Sous-classe concrète — appel sans reference_audio_path (rétrocompat) ──
section("Sous-classe concrète — appel sans reference_audio_path (rétrocompat)")


class _FakeTTS(BaseTTSProvider):
    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        return b"fake_wav"


import asyncio  # noqa: E402

_fake = _FakeTTS()
result = asyncio.run(_fake.synthesise("Bonjour.", "male_0"))
assert result == b"fake_wav"
ok("synthesise(text, voice_id) sans reference_audio_path — pas de crash")


# ── 9. Sous-classe concrète — appel avec reference_audio_path ────────────────
section("Sous-classe concrète — appel avec reference_audio_path='path/to/ref.wav'")

captured: list[str | None] = []


class _FakeTTSCapture(BaseTTSProvider):
    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        captured.append(reference_audio_path)
        return b"ok"


asyncio.run(_FakeTTSCapture().synthesise("Hello.", "cloned_0", reference_audio_path="refs/voice.wav"))
assert captured == ["refs/voice.wav"], f"Obtenu : {captured}"
ok("reference_audio_path transmis jusqu'à la méthode")


# ── 10. Signatures — tous les 3 providers concrets ────────────────────────────
section("Tous les 3 providers concrets — synthesise accepte reference_audio_path")

from app.services.tts.edgetts import EdgeTTSProvider  # noqa: E402
from app.services.tts.piper import PiperProvider  # noqa: E402
from app.services.tts.qwen import QwenTTSProvider  # noqa: E402

_PROVIDERS_TO_CHECK = [
    (EdgeTTSProvider, "EdgeTTSProvider"),
    (PiperProvider, "PiperProvider"),
    (QwenTTSProvider, "QwenTTSProvider"),
]
for _cls, _cname in _PROVIDERS_TO_CHECK:
    _sig = inspect.signature(_cls.synthesise)
    if "reference_audio_path" not in _sig.parameters:
        die(f"{_cname}.synthesise: reference_audio_path absent -- params: {list(_sig.parameters)}")
    _p = _sig.parameters["reference_audio_path"]
    if _p.default is not None:
        die(f"{_cname}.synthesise: reference_audio_path doit defaut a None, obtenu: {_p.default!r}")
ok("EdgeTTS / Piper / Qwen -- reference_audio_path: str | None = None")


# ── 11. QwenTTS chemin clone — generate_voice_clone appele ───────────────────
section("QwenTTSProvider clone: generate_voice_clone appele, WAV 22050 Hz produit")

import io as _io  # noqa: E402
import wave as _wave  # noqa: E402
from unittest.mock import patch as _patch  # noqa: E402
import app.services.tts.qwen as _qwen_mod  # noqa: E402
from app.services.tts.qwen import QwenTTSProvider as _QwenTTS  # noqa: E402


class _FakeCuda:
    @staticmethod
    def empty_cache() -> None: pass


class _FakeTorchBase:
    bfloat16 = "bf16-sentinel"
    cuda = _FakeCuda


class _FakeBaseModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_voice_clone(self, **kwargs):
        self.calls.append(kwargs)
        return [[0.0] * 480], 24000


class _FakeBaseModelCls:
    _last: "_FakeBaseModel | None" = None

    @classmethod
    def from_pretrained(cls, *a, **kw):
        cls._last = _FakeBaseModel()
        return cls._last


def _fake_deps_base():
    return _FakeTorchBase(), _FakeBaseModelCls


_mock_s11 = MagicMock()
_mock_s11.qwen_model = "1.7b"
_mock_s11.qwen_language = "French"
_mock_s11.qwen_device = "cuda:0"
_mock_s11.qwen_attn = "sdpa"

_fake_ref_audio = ([0.0] * 100, 24000)


async def _call_clone_path():
    p = _QwenTTS(_mock_s11)
    with (
        _patch.object(_qwen_mod, "_import_qwen_deps", side_effect=_fake_deps_base),
        _patch.object(_qwen_mod, "_load_ref_audio", return_value=_fake_ref_audio),
    ):
        wav = await p.synthesise("Bonjour.", "cloned_slug", reference_audio_path="refs/voice.wav")
    return p, wav


_p11, _wav11 = asyncio.run(_call_clone_path())
if _p11._base_model is None:
    die("_base_model doit etre charge apres un appel clone")
if len(_p11._base_model.calls) != 1:
    die(f"generate_voice_clone doit etre appele une fois, obtenu {len(_p11._base_model.calls)}")
if "ref_audio" not in _p11._base_model.calls[0]:
    die(f"ref_audio absent des kwargs: {list(_p11._base_model.calls[0])}")
with _wave.open(_io.BytesIO(_wav11), "rb") as _w11:
    if _w11.getframerate() != 22050:
        die(f"framerate attendu 22050, obtenu {_w11.getframerate()}")
ok("generate_voice_clone appele avec ref_audio, WAV 22050 Hz produit")


# ── 12. QwenTTS swap — charger le modele Base decharge le CustomVoice ────────
section("QwenTTSProvider swap: charger Base decharge CustomVoice (VRAM sequentiel)")


class _FakeCustomModel:
    def generate_custom_voice(self, **kwargs):
        return [[0.0] * 480], 24000


class _FakeCustomModelCls:
    @classmethod
    def from_pretrained(cls, *a, **kw):
        return _FakeCustomModel()


def _fake_deps_custom():
    return _FakeTorchBase(), _FakeCustomModelCls


async def _call_swap():
    p = _QwenTTS(_mock_s11)
    with _patch.object(_qwen_mod, "_import_qwen_deps", side_effect=_fake_deps_custom):
        await p.synthesise("Hello.", "narrator")
    assert p._model is not None, "Custom model doit etre charge apres un appel preset"
    assert p._base_model is None, "Base model ne doit pas etre charge apres un appel preset"
    with (
        _patch.object(_qwen_mod, "_import_qwen_deps", side_effect=_fake_deps_base),
        _patch.object(_qwen_mod, "_load_ref_audio", return_value=_fake_ref_audio),
    ):
        await p.synthesise("Hello.", "cloned_0", reference_audio_path="refs/voice.wav")
    return p


_p12 = asyncio.run(_call_swap())
if _p12._model is not None:
    die("CustomVoice doit etre decharge apres chargement du modele Base")
if _p12._base_model is None:
    die("Base model doit etre charge")
ok("swap: CustomVoice decharge, Base charge (sequentiel)")


# ── 13. synthesise_chapter — reference_audio_path lu en DB et transmis ───────
section("synthesise_chapter: reference_audio_path lu depuis Voice DB et passe a tts")

from sqlalchemy.pool import StaticPool as _SPool  # noqa: E402
from sqlmodel import Session as _Sess, SQLModel as _SQL, create_engine as _ce, select as _sel  # noqa: E402
from app.models.entities import (  # noqa: E402
    Book as _Book, Chapter as _Chapter, Character as _Char, Segment as _Seg, Voice as _Voice,
)
from app.core.enums import SegmentType as _ST, VoiceKind as _VK  # noqa: E402
from app.services.audio.chapter import synthesise_chapter  # noqa: E402


def _silence_wav() -> bytes:
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 100)
    return buf.getvalue()


_s13_engine = _ce("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=_SPool)
_SQL.metadata.create_all(_s13_engine)

with _Sess(_s13_engine) as _s:
    _b13 = _Book(title="T", source_path="/x.epub"); _s.add(_b13); _s.flush()
    _c13 = _Chapter(book_id=_b13.id, position=1, raw_text="x"); _s.add(_c13); _s.flush()
    _char13 = _Char(book_id=_b13.id, name="Alice", voice_id="male_0"); _s.add(_char13); _s.flush()
    _s.add(_Seg(chapter_id=_c13.id, position=1, text="Bonjour.",
               segment_type=_ST.DIALOGUE, character_id=_char13.id))
    _s.add(_Voice(voice_id="male_0", name="Male 0", kind=_VK.CLONED,
                  reference_audio_path="data/voices/alice/ref.wav"))
    _s.commit()
    _c13_id = _c13.id

_s13_calls: list[dict] = []


class _Cap13(BaseTTSProvider):
    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        _s13_calls.append({"vid": voice_id, "ref": reference_audio_path})
        return _silence_wav()


with _Sess(_s13_engine) as _s:
    asyncio.run(synthesise_chapter(_c13_id, _s, _Cap13()))

if len(_s13_calls) != 1:
    die(f"Expected 1 call, got {len(_s13_calls)}")
if _s13_calls[0]["vid"] != "male_0":
    die(f"voice_id should be 'male_0', got {_s13_calls[0]['vid']!r}")
if _s13_calls[0]["ref"] != "data/voices/alice/ref.wav":
    die(f"reference_audio_path should be set, got {_s13_calls[0]['ref']!r}")
ok("Voice.reference_audio_path transmis a tts.synthesise")


# ── 14. synthesise_chapter — pas de Voice en DB -> None transmis (retro-compat)
section("synthesise_chapter: pas de Voice en DB -> reference_audio_path=None")

_s14_engine = _ce("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=_SPool)
_SQL.metadata.create_all(_s14_engine)

with _Sess(_s14_engine) as _s:
    _b14 = _Book(title="T", source_path="/x.epub"); _s.add(_b14); _s.flush()
    _c14 = _Chapter(book_id=_b14.id, position=1, raw_text="x"); _s.add(_c14); _s.flush()
    _char14 = _Char(book_id=_b14.id, name="Bob", voice_id="narrator"); _s.add(_char14); _s.flush()
    _s.add(_Seg(chapter_id=_c14.id, position=1, text="Hi.",
               segment_type=_ST.DIALOGUE, character_id=_char14.id))
    # No Voice entity in DB
    _s.commit()
    _c14_id = _c14.id

_s14_calls: list[dict] = []


class _Cap14(BaseTTSProvider):
    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        _s14_calls.append({"vid": voice_id, "ref": reference_audio_path})
        return _silence_wav()


with _Sess(_s14_engine) as _s:
    asyncio.run(synthesise_chapter(_c14_id, _s, _Cap14()))

if len(_s14_calls) != 1:
    die(f"Expected 1 call, got {len(_s14_calls)}")
if _s14_calls[0]["ref"] is not None:
    die(f"reference_audio_path should be None when no Voice in DB, got {_s14_calls[0]['ref']!r}")
ok("no Voice in DB -> reference_audio_path=None (retro-compat)")


# ══ Étape 4 — API REST voix ════════════════════════════════════════════════════
import tempfile as _tempfile  # noqa: E402
from unittest.mock import patch as _mpatch  # noqa: E402

from fastapi.testclient import TestClient as _TC  # noqa: E402
from app.main import app as _app  # noqa: E402
from app.core.db import get_session as _get_session  # noqa: E402
from app.api.routes import voices as _voices_mod  # noqa: E402
from app.core.enums import VoiceKind as _VoiceKind  # noqa: E402

_v_engine = _ce("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=_SPool)
_SQL.metadata.create_all(_v_engine)


def _v_session():
    with _Sess(_v_engine) as _s:
        yield _s


_app.dependency_overrides[_get_session] = _v_session

# Seed CATALOGUE voices: narrator pour §19 (inspecté), male_0 pour §18 (supprimé)
with _Sess(_v_engine) as _s:
    _s.add(_Voice(voice_id="narrator", name="Narrator", kind=_VoiceKind.CATALOGUE))
    _s.add(_Voice(voice_id="male_0", name="Male 0", kind=_VoiceKind.CATALOGUE))
    _s.commit()


# ── 15. POST /voices — happy path ─────────────────────────────────────────────
section("POST /voices -- happy path (201, Voice en DB, fichier sur disque)")

with _tempfile.TemporaryDirectory() as _tmp15:
    _tmp15_path = Path(_tmp15)
    with _mpatch.object(_voices_mod, "DATA_DIR", _tmp15_path):
        with _TC(_app, raise_server_exceptions=False) as _tc15:
            _r15 = _tc15.post(
                "/voices",
                data={"name": "Test Clone", "gender": "MALE"},
                files={"file": ("sample.wav", _silence_wav(), "audio/wav")},
            )
    if _r15.status_code != 201:
        die(f"Expected 201, got {_r15.status_code}: {_r15.text}")
    _d15 = _r15.json()
    if _d15.get("id") != "test-clone":
        die(f"Expected id='test-clone', got {_d15.get('id')!r}")
    if not _d15.get("has_reference_audio"):
        die(f"has_reference_audio should be True, got {_d15.get('has_reference_audio')!r}")
    # File on disk
    _ref15 = _tmp15_path / "voices" / "test-clone" / "ref.wav"
    if not _ref15.exists():
        die(f"Reference file not found at {_ref15}")
ok("201 + Voice en DB + fichier ref sur disque")


# ── 16. POST /voices — doublon -> 409 ─────────────────────────────────────────
section("POST /voices -- slug en double -> 409")

with _tempfile.TemporaryDirectory() as _tmp16:
    with _mpatch.object(_voices_mod, "DATA_DIR", Path(_tmp16)):
        with _TC(_app, raise_server_exceptions=False) as _tc16:
            _tc16.post("/voices",
                data={"name": "Test Clone"},
                files={"file": ("s.wav", _silence_wav(), "audio/wav")})
            _r16 = _tc16.post("/voices",
                data={"name": "Test Clone"},
                files={"file": ("s.wav", _silence_wav(), "audio/wav")})
    if _r16.status_code != 409:
        die(f"Expected 409 on duplicate, got {_r16.status_code}: {_r16.text}")
ok("409 sur slug duplique")


# ── 17. DELETE /voices/{id} — voix CLONED -> 204 ─────────────────────────────
section("DELETE /voices/{id} -- voix CLONED -> 204, fichier supprime")

with _tempfile.TemporaryDirectory() as _tmp17:
    _tmp17_path = Path(_tmp17)
    with _mpatch.object(_voices_mod, "DATA_DIR", _tmp17_path):
        with _TC(_app, raise_server_exceptions=False) as _tc17:
            _tc17.post("/voices",
                data={"name": "To Delete"},
                files={"file": ("r.wav", _silence_wav(), "audio/wav")})
    _ref17 = _tmp17_path / "voices" / "to-delete" / "ref.wav"
    if not _ref17.exists():
        die("Setup failed: reference file not created")
    with _mpatch.object(_voices_mod, "DATA_DIR", _tmp17_path):
        with _TC(_app, raise_server_exceptions=False) as _tc17b:
            _r17 = _tc17b.delete("/voices/to-delete")
    if _r17.status_code != 204:
        die(f"Expected 204, got {_r17.status_code}: {_r17.text}")
    if _ref17.exists():
        die("Reference file should have been deleted")
    with _Sess(_v_engine) as _s:
        _gone = _s.exec(_sel(_Voice).where(_Voice.voice_id == "to-delete")).first()
        if _gone is not None:
            die("Voice should be deleted from DB")
ok("204 + fichier supprime + Voice retiree de la DB")


# ── 18. DELETE /voices/{id} — voix CATALOGUE -> 204 (autorisé, re-seedé au restart) ───
# N.B. On utilise male_0 (pas narrator) pour ne pas casser le §19 qui l'inspecte.
section("DELETE /voices/{id} -- voix CATALOGUE -> 204 (autorise, re-seede au restart)")

with _TC(_app, raise_server_exceptions=False) as _tc18:
    _r18 = _tc18.delete("/voices/male_0")
if _r18.status_code != 204:
    die(f"Expected 204 for CATALOGUE voice delete, got {_r18.status_code}: {_r18.text}")
with _Sess(_v_engine) as _s18:
    _gone18 = _s18.exec(_sel(_Voice).where(_Voice.voice_id == "male_0")).first()
    if _gone18 is not None:
        die("CATALOGUE voice male_0 should have been removed from DB")
ok("204 + retiree de la DB (re-seedee au prochain demarrage)")


# ── 19. GET /voices — has_reference_audio correct ────────────────────────────
section("GET /voices -- has_reference_audio = True pour CLONED, False pour CATALOGUE")

with _TC(_app, raise_server_exceptions=False) as _tc19:
    _r19 = _tc19.get("/voices")
if _r19.status_code != 200:
    die(f"Expected 200, got {_r19.status_code}")
_voices19 = {v["id"]: v for v in _r19.json()}
if "narrator" not in _voices19:
    die("narrator not in voices list")
if _voices19["narrator"].get("has_reference_audio"):
    die("CATALOGUE voice narrator should have has_reference_audio=False")
# test-clone was created in section 15 (same _v_engine) — should still be in DB
if "test-clone" in _voices19:
    if not _voices19["test-clone"].get("has_reference_audio"):
        die("CLONED voice test-clone should have has_reference_audio=True")
    ok("CATALOGUE=False, CLONED=True")
else:
    ok("CATALOGUE=False (CLONED already cleaned up)")

_app.dependency_overrides.clear()


print(f"\nPHASE 18 Etapes 1-4 (contrat + providers + pipeline + API) OK -- {_n}/{_n} sections\n")
