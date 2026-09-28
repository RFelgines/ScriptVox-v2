"""check_phase51.py — moteur TTS OmniVoice (serveur local) et voix conçues par personnage.

Le serveur OmniVoice est simulé (httpx patché) : ces tests ne demandent ni GPU ni modèle.
Le rendu réel est vérifié à part (scripts/omnivoice_server.py, mesures dans sa docstring).

Run: python tests/check_phase51.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="sv_p51_"))
os.environ.update({
    "LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3", "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p51.db", "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": str(_TMP / "data"), "TTS_PROVIDER": "edgetts",
})
for k in ("OMNIVOICE_URL", "OMNIVOICE_NUM_STEP", "OMNIVOICE_VOICE_MAP"):
    os.environ.pop(k, None)

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


import httpx  # noqa: E402

from app.config import Settings  # noqa: E402
from app.services import registry  # noqa: E402
from app.services.audio.format import silence_wav  # noqa: E402
from app.services.tts import omnivoice  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402


class _FakeServer:
    """Remplace httpx.AsyncClient.post : mémorise les requêtes, renvoie un WAV."""

    def __init__(self, status=200):
        self.requests: list[tuple[str, dict]] = []
        self.status = status

    async def post(self, client, url, json=None, **_):  # noqa: A002 — signature httpx
        self.requests.append((url, json))
        if url.endswith("/design"):
            out = Path(json["out_path"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(silence_wav(300))
            out.with_suffix(".txt").write_text("Le soir tombait.", encoding="utf-8")
            return httpx.Response(self.status, json={"path": str(out), "reference_text": "Le soir tombait."})
        return httpx.Response(self.status, content=silence_wav(500) if self.status == 200 else b"boom")


def _serve(fake):
    async def _post(client, url, json=None, **kw):
        return await fake.post(client, url, json=json, **kw)
    return patch.object(httpx.AsyncClient, "post", _post)


# ── 1. Description de voix d'un personnage ────────────────────────────────────
section("Description OmniVoice déduite de la fiche du personnage")
cases = [
    (("MALE", "ELDER", "voix grave et rauque", None, None), "male, elderly, low pitch"),
    (("FEMALE", "YOUNG_ADULT", None, "claire", None), "female, young adult, high pitch"),
    (("FEMALE", "ADULT", None, None, "parle toujours en chuchotant"), "female, middle-aged, whisper"),
    (("UNKNOWN", "UNKNOWN", None, None, None), "moderate pitch"),
    (("MALE", "CHILD", "bright", None, None), "male, child, high pitch"),
]
for args, attendu in cases:
    got = omnivoice.instruct_for_character(*args)
    check(f"{args[:3]} -> {attendu!r}", got == attendu, repr(got))

section("Émotion -> débit (OmniVoice n'a pas de contrôle d'émotion)")
check("colère -> plus vite", omnivoice.speed_for("en colère") == 1.08)
check("triste -> plus lent", omnivoice.speed_for("triste, las") == 0.92)
check("neutre -> inchangé", omnivoice.speed_for("amusée") is None and omnivoice.speed_for(None) is None)


# ── 2. Moteur : requêtes envoyées au serveur ──────────────────────────────────
section("Moteur omnivoice : voix du catalogue, clonage, erreurs")
settings = Settings()
p = registry.build_tts_provider("omnivoice", settings, {"num_step": 16}, language="fr-FR")
check("enregistré au registre, clonage déclaré", p.supports_cloning is True
      and "omnivoice" in registry.available_tts_providers() if hasattr(registry, "available_tts_providers")
      else p.supports_cloning is True)
fake = _FakeServer()
with _serve(fake):
    wav = asyncio.run(p.synthesise("Bonjour.", "male_2", emotion="furieux"))
url, body = fake.requests[-1]
check("POST {OMNIVOICE_URL}/synthesize", url == "http://127.0.0.1:8770/synthesize", url)
check("voix du catalogue -> description conçue (pas de référence)",
      body["instruct"] == "male, elderly, low pitch" and "ref_audio_path" not in body, str(body))
check("langue du livre (2 lettres), étapes à chaud, débit d'émotion",
      body["language"] == "fr" and body["num_step"] == 16 and body["speed"] == 1.08, str(body))
check("renvoie l'audio du serveur", wav[:4] == b"RIFF")

ref = _TMP / "voices" / "x" / "ref.wav"
ref.parent.mkdir(parents=True)
ref.write_bytes(silence_wav(100))
ref.with_suffix(".txt").write_text("Transcription.", encoding="utf-8")
with _serve(fake):
    asyncio.run(p.synthesise("Salut.", "design_b1_c2", reference_audio_path=str(ref)))
body = fake.requests[-1][1]
check("voix clonée -> ref_audio_path + transcription (.txt), sans description",
      body["ref_audio_path"] == str(ref) and body["ref_text"] == "Transcription." and "instruct" not in body,
      str(body))
try:
    asyncio.run(p.synthesise("x", "voix_inconnue"))
    check("voice_id inconnu sans référence -> TTSError", False)
except TTSError:
    check("voice_id inconnu sans référence -> TTSError", True)
with _serve(_FakeServer(status=500)):
    try:
        asyncio.run(p.synthesise("x", "narrator"))
        check("erreur serveur -> TTSError", False)
    except TTSError as exc:
        check("erreur serveur -> TTSError explicite", "HTTP 500" in str(exc), str(exc))


async def _down(client, url, json=None, **_):
    raise httpx.ConnectError("refused")

with patch.object(httpx.AsyncClient, "post", _down):
    try:
        asyncio.run(p.synthesise("x", "narrator"))
        check("serveur éteint -> TTSError", False)
    except TTSError as exc:
        check("serveur éteint -> TTSError qui dit comment le lancer",
              "omnivoice_server.py" in str(exc), str(exc))

os.environ["OMNIVOICE_VOICE_MAP"] = json.dumps({"narrator": "female, middle-aged, low pitch"})
p2 = registry.build_tts_provider("omnivoice", Settings(), None, language="en")
check("OMNIVOICE_VOICE_MAP surcharge une description", p2.resolve_voice("narrator") == "female, middle-aged, low pitch")
os.environ.pop("OMNIVOICE_VOICE_MAP")


# ── 3. Voix conçue d'un personnage, bout en bout ──────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.enums import AgeCategory, BookStatus, Gender, SegmentType, VoiceKind  # noqa: E402
from app.models import Book, Chapter, Character, Segment  # noqa: E402
from app.models.entities import Voice  # noqa: E402
from app.services.tts.base import BaseTTSProvider  # noqa: E402
from app.services.voice_assignment import assign_voices, seed_catalogue_voices  # noqa: E402
from app.workers import tasks  # noqa: E402


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        seed_catalogue_voices(s)
    return eng


eng = _engine()
with Session(eng) as s:
    b = Book(title="Lettres", source_path=str(_TMP / "l.epub"), status=BookStatus.ANALYZED, language="fr")
    s.add(b); s.commit(); s.refresh(b)
    meunier = Character(book_id=b.id, name="Maître Cornille", gender=Gender.MALE,
                        age_category=AgeCategory.ELDER, voice_quality="grave", voice_id="male_0")
    s.add(meunier); s.commit(); s.refresh(meunier)
    c = Chapter(book_id=b.id, position=1, title="Un", raw_text="x")
    s.add(c); s.commit(); s.refresh(c)
    s.add(Segment(chapter_id=c.id, position=1, text="Narration.", segment_type=SegmentType.NARRATION))
    s.add(Segment(chapter_id=c.id, position=2, text="Réplique.", segment_type=SegmentType.DIALOGUE,
                  character_id=meunier.id))
    s.commit()
    book_id, char_id, chapter_id = b.id, meunier.id, c.id

section("Voix conçue : API de description")
from app.core.db import get_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


def _sess():
    with Session(eng) as s:
        yield s


fastapi_app.dependency_overrides[get_session] = _sess
client = TestClient(fastapi_app)
r = client.get(f"/characters/{char_id}/voice-design")
check("GET -> description proposée depuis la fiche, pas encore de voix conçue",
      r.status_code == 200 and r.json()["suggested_instruct"] == "male, elderly, low pitch"
      and r.json()["designed_voice_id"] is None, r.text)
queued = []
with patch("app.workers.tasks.design_character_voice", side_effect=lambda *a: queued.append(a)):
    r = client.post(f"/characters/{char_id}/voice-design", json={"instruct": "male, elderly, whisper"})
check("POST -> 202, tâche enfilée avec la description modifiée",
      r.status_code == 202 and queued == [(char_id, "male, elderly, whisper")]
      and r.json()["voice_id"] == f"design_b{book_id}_c{char_id}", f"{r.text} {queued}")
check("personnage inconnu -> 404", client.get("/characters/999/voice-design").status_code == 404)

section("Voix conçue : tâche (serveur simulé)")
fake = _FakeServer()
with patch("app.core.db.get_engine", return_value=eng), _serve(fake):
    vid = tasks._design_character_voice_impl(char_id)
with Session(eng) as s:
    ch = s.get(Character, char_id)
    v = s.exec(select(Voice).where(Voice.voice_id == vid)).first()
design_req = [b for u, b in fake.requests if u.endswith("/design")]
check("le serveur reçoit la description et la langue du livre",
      design_req and design_req[0]["instruct"] == "male, elderly, low pitch" and design_req[0]["language"] == "fr",
      str(design_req))
check("voix CLONED créée avec échantillon et transcription",
      v is not None and v.kind == VoiceKind.CLONED and Path(v.reference_audio_path).is_file()
      and v.reference_text == "Le soir tombait." and v.gender == Gender.MALE, str(v))
check("voix attribuée au personnage", ch.voice_id == vid == f"design_b{book_id}_c{char_id}", str(ch.voice_id))
check("description conservée à côté de l'échantillon (design.json)",
      json.loads((Path(v.reference_audio_path).parent / "design.json").read_text(encoding="utf-8"))["instruct"]
      == "male, elderly, low pitch")
r = client.get(f"/characters/{char_id}/voice-design")
check("GET après conception -> voix conçue actuelle et attribuée",
      r.json()["current_instruct"] == "male, elderly, low pitch" and r.json()["assigned"] is True, r.text)
with patch("app.core.db.get_engine", return_value=eng), _serve(fake):
    tasks._design_character_voice_impl(char_id, "male, elderly, whisper")
with Session(eng) as s:
    n = len(s.exec(select(Voice).where(Voice.voice_id == vid)).all())
check("reconcevoir remplace la même voix (pas de doublon)", n == 1)
with patch("app.core.db.get_engine", return_value=eng), _serve(_FakeServer(status=500)):
    check("échec du serveur -> None, rien ne lève", tasks._design_character_voice_impl(char_id) is None)
fastapi_app.dependency_overrides.clear()


# ── 4. Rendu : moteur qui clone vs moteur qui ne clone pas ────────────────────
class _Rec(BaseTTSProvider):
    def __init__(self, cloning):
        self.supports_cloning = cloning
        self.calls = []

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        self.calls.append((text, voice_id, reference_audio_path))
        return silence_wav(200)


from app.services.audio.chapter import _synthesise_segments  # noqa: E402

section("Rendu d'un chapitre avec la voix conçue")
with Session(eng) as s:
    rec = _Rec(cloning=True)
    asyncio.run(_synthesise_segments(chapter_id, s, rec))
dlg = [c for c in rec.calls if c[0] == "Réplique."][0]
check("moteur qui clone : réplique rendue avec l'échantillon de la voix conçue",
      dlg[1] == vid and dlg[2] and dlg[2].endswith("ref.wav"), str(dlg))
with Session(eng) as s:
    rec = _Rec(cloning=False)
    asyncio.run(_synthesise_segments(chapter_id, s, rec))
dlg = [c for c in rec.calls if c[0] == "Réplique."][0]
check("moteur sans clonage (EdgeTTS…) : voix du catalogue du même genre, pas d'échec",
      dlg[1] == "male_0" and dlg[2] is None, str(dlg))

section("Attribution : les voix clonées sont prioritaires pour omnivoice comme pour qwen")
with Session(eng) as s:
    s.add(Voice(voice_id="ma_voix", name="Ma voix", kind=VoiceKind.CLONED, gender=Gender.FEMALE,
                reference_audio_path=str(ref)))
    heroine = Character(book_id=book_id, name="Vivette", gender=Gender.FEMALE)
    s.add(heroine); s.commit(); s.refresh(heroine)
    assign_voices(book_id, s, tts_provider="omnivoice")
    s.commit()
    check("omnivoice : voix clonée de la bibliothèque attribuée d'abord",
          s.get(Character, heroine.id).voice_id == "ma_voix")
    h2 = Character(book_id=book_id, name="Bénézet", gender=Gender.FEMALE)
    s.add(h2); s.commit(); s.refresh(h2)
    assign_voices(book_id, s, tts_provider="edgetts")
    s.commit()
    check("edgetts : catalogue seulement", s.get(Character, h2.id).voice_id.startswith("female_"))


print()
if _errors:
    print(f"ÉCHEC : {len(_errors)} vérification(s)")
    sys.exit(1)
print("OK : toutes les vérifications passent")
