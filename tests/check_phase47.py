"""check_phase47.py — audit 2026-09-25 : changement de modèle facile, moteurs non officiels.

Verifie :
  - registre + plugins (llm/tts) : chargement, erreurs isolées, noms réservés ;
  - providers génériques : LLM « compatible OpenAI » (repli json_schema -> json_object),
    TTS « compatible OpenAI » (table de voix, corps additionnel, émotion), TTS « commande »
    (aucune injection shell, code de sortie, stdout) ;
  - réglages à chaud (model, base_url) : API /settings, validation, liste de modèles ;
  - options transmises aux providers officiels (Ollama, Qwen checkpoint libre, EdgeTTS) ;
  - voix EdgeTTS françaises dédoublonnées.

Run: python tests/check_phase47.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="sv_p47_"))
_PLUG = _TMP / "plugins"
(_PLUG / "llm").mkdir(parents=True)
(_PLUG / "tts").mkdir(parents=True)

os.environ.update({
    "LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3", "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p47.db", "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": str(_TMP / "data"), "TTS_PROVIDER": "edgetts",
    "PLUGINS_DIR": str(_PLUG),
})

_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    ok  {label}")
    else:
        msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


# ── plugins déposés par l'utilisateur ────────────────────────────────────────
(_PLUG / "tts" / "tone.py").write_text(textwrap.dedent('''
    PROVIDER_NAME = "tone"
    DESCRIPTION = "Bip de test"
    def list_models(settings, options):
        return ["tone-a", "tone-b"]
    def create(settings, options, language=None):
        from app.services.tts.base import BaseTTSProvider
        from app.services.audio.format import silence_wav
        class Tone(BaseTTSProvider):
            model = options.get("model", "default")
            async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
                return silence_wav(500)
        return Tone()
'''))
(_PLUG / "llm" / "echo.py").write_text(textwrap.dedent('''
    PROVIDER_NAME = "echo"
    def create(settings, options):
        from app.services.llm.base import BaseLLMProvider
        class Echo(BaseLLMProvider):
            async def analyze(self, text, known_characters=None, language=None): raise NotImplementedError
            async def suggest_merges(self, characters): return []
        return Echo()
'''))
(_PLUG / "tts" / "broken.py").write_text("raise RuntimeError('plugin cassé')\n")
(_PLUG / "tts" / "nofunc.py").write_text("PROVIDER_NAME = 'nofunc'\n")
(_PLUG / "tts" / "piper.py").write_text("PROVIDER_NAME='piper'\ndef create(s,o): return None\n")
(_PLUG / "tts" / "_ignored.py").write_text("PROVIDER_NAME = 'ignored'\ndef create(s,o): return None\n")

from app.services import registry  # noqa: E402

print("[1] registre : providers officiels + plugins")
registry.load_plugins(force=True)
check("plugin TTS chargé", "tone" in registry.tts_provider_names())
check("plugin LLM chargé", "echo" in registry.llm_provider_names())
check("officiels toujours présents",
      {"edgetts", "piper", "qwen", "openai_tts", "command"} <= set(registry.tts_provider_names())
      and {"ollama", "gemini", "openai_compatible"} <= set(registry.llm_provider_names()))
check("fichier commençant par _ ignoré", "ignored" not in registry.tts_provider_names())
errs = {e["file"].replace("\\", "/"): e["error"] for e in registry.plugin_errors()}
check("plugin cassé isolé et signalé", "tts/broken.py" in errs and "cassé" in errs["tts/broken.py"], str(errs))
check("plugin sans create() signalé", "tts/nofunc.py" in errs)
check("nom réservé par un officiel refusé", "tts/piper.py" in errs and "officiel" in errs["tts/piper.py"], str(errs))
check("descriptions exposées", registry.provider_descriptions("tts")["tone"] == "Bip de test")
check("suggestions de modèles d'un plugin", registry.plugin_list_models("tts", "tone", None, {}) == ["tone-a", "tone-b"])

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()
settings = get_settings()

from app.services.tts.factory import get_tts_provider  # noqa: E402
from app.services.llm.factory import get_llm_provider  # noqa: E402

p = get_tts_provider(settings, override="tone", options={"model": "tone-b"})
check("get_tts_provider résout un plugin avec ses options", type(p).__name__ == "Tone" and p.model == "tone-b")
wav = asyncio.run(p.synthesise("x", "narrator"))
check("le plugin synthétise", wav[:4] == b"RIFF")
check("get_llm_provider résout un plugin LLM", type(get_llm_provider(settings, override="echo")).__name__ == "Echo")
for bad_call in (lambda: get_tts_provider(settings, override="nexistepas"),
                 lambda: get_llm_provider(settings, override="nexistepas")):
    try:
        bad_call()
        check("provider inconnu -> ValueError", False)
    except ValueError as exc:
        check("provider inconnu -> ValueError listant les valeurs acceptées", "tone" in str(exc) or "echo" in str(exc))

os.environ["TTS_PROVIDER"] = "tone"
get_settings.cache_clear()
check("un plugin peut être le provider par défaut du .env", get_settings().tts_provider == "tone")
os.environ["TTS_PROVIDER"] = "nexistepas"
get_settings.cache_clear()
try:
    get_settings()
    check("TTS_PROVIDER inconnu -> fail-fast", False)
except ValueError as exc:
    check("TTS_PROVIDER inconnu -> fail-fast avec la liste", "tone" in str(exc))
os.environ["TTS_PROVIDER"] = "edgetts"
get_settings.cache_clear()
settings = get_settings()


# ── faux serveur HTTP (loopback) ────────────────────────────────────────────
_requests: list[dict] = []
_REFUSE_SCHEMA = {"on": True}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": "qwen3.8-27b"}, {"id": "llama-x"}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        _requests.append({"path": self.path, "body": payload, "auth": self.headers.get("Authorization")})
        if self.path.endswith("/chat/completions"):
            rf = payload.get("response_format", {})
            if rf.get("type") == "json_schema" and _REFUSE_SCHEMA["on"]:
                self.send_response(400); self.end_headers(); self.wfile.write(b'{"error":"unsupported"}')
                return
            content = json.dumps({
                "characters": [{"name": "Alice", "gender": "FEMALE"}],
                "attributions": [{"index": 1, "character_name": "Alice", "emotion": "calm"}],
            })
            if rf.get("type") != "json_object":
                content = "Voici :\n```json\n" + content + "\n```"
            body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path.endswith("/audio/speech"):
            from app.services.audio.format import pcm16_to_wav
            body = pcm16_to_wav(b"\x10\x00" * 8000, 8000)
            self.send_response(200); self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()


_server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
threading.Thread(target=_server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{_server.server_address[1]}/v1"

print("\n[2] LLM « compatible OpenAI » : n'importe quel serveur, n'importe quel modèle")
os.environ.update({"OPENAI_BASE_URL": BASE, "OPENAI_MODEL": "qwen3.8-27b", "OPENAI_API_KEY": "sk-test"})
get_settings.cache_clear()
settings = get_settings()
llm = get_llm_provider(settings, override="openai_compatible")
res = asyncio.run(llm.analyze("« Bonjour », dit Alice."))
check("analyse réussie via /chat/completions", [c.name for c in res.characters] == ["Alice"], str(res.characters))
check("l'attribution est appliquée", any(s.character_name == "Alice" for s in res.segments))
modes = [r["body"].get("response_format", {}).get("type", "text") for r in _requests if r["path"].endswith("/chat/completions")]
check("json_schema tenté d'abord puis repli json_object", modes[:2] == ["json_schema", "json_object"], str(modes))
check("clé API envoyée en Bearer", _requests[0]["auth"] == "Bearer sk-test")
check("le modèle du .env est utilisé", _requests[0]["body"]["model"] == "qwen3.8-27b")
_requests.clear()
asyncio.run(llm.analyze("« Encore », dit Alice."))
check("le mode accepté est mémorisé (pas de nouveau test)",
      [r["body"].get("response_format", {}).get("type") for r in _requests] == ["json_object"])
llm2 = get_llm_provider(settings, override="openai_compatible", options={"model": "autre-modele", "base_url": BASE})
_requests.clear()
asyncio.run(llm2.analyze("« Hop », dit Alice."))
check("option à chaud `model` prioritaire sur le .env", _requests[0]["body"]["model"] == "autre-modele")
_REFUSE_SCHEMA["on"] = False
llm3 = get_llm_provider(settings, override="openai_compatible")
_requests.clear()
res3 = asyncio.run(llm3.analyze("« Hop », dit Alice."))
check("réponse entourée de ```json``` correctement extraite", [c.name for c in res3.characters] == ["Alice"])
from app.services.llm.openai_compatible import list_openai_models  # noqa: E402
check("liste des modèles du serveur", list_openai_models(BASE, None) == ["llama-x", "qwen3.8-27b"])
os.environ.pop("OPENAI_MODEL")
get_settings.cache_clear()
try:
    get_llm_provider(get_settings(), override="openai_compatible")
    check("aucun modèle défini -> erreur claire", False)
except Exception as exc:  # noqa: BLE001
    check("aucun modèle défini -> erreur claire", "OPENAI_MODEL" in str(exc), str(exc))
os.environ["OPENAI_MODEL"] = "qwen3.8-27b"
get_settings.cache_clear()
settings = get_settings()

print("\n[3] TTS « compatible OpenAI »")
os.environ.update({
    "TTS_HTTP_BASE_URL": BASE, "TTS_HTTP_MODEL": "kokoro",
    "TTS_HTTP_VOICE_MAP": json.dumps({"narrator": "ff_siwis", "default": "af_x"}),
    "TTS_HTTP_EXTRA_BODY": json.dumps({"speed": 0.9}),
    "TTS_HTTP_EMOTION_FIELD": "style",
})
get_settings.cache_clear()
settings = get_settings()
tts = get_tts_provider(settings, override="openai_tts")
_requests.clear()
out = asyncio.run(tts.synthesise("Bonjour", "narrator", emotion="joyeux"))
body = _requests[0]["body"]
check("voix logique mappée", body["voice"] == "ff_siwis", str(body))
check("corps additionnel fusionné", body["speed"] == 0.9 and body["model"] == "kokoro")
check("émotion envoyée dans le champ configuré", body["style"] == "joyeux")
check("texte envoyé", body["input"] == "Bonjour")
from app.services.audio.format import wav_info  # noqa: E402
check("sortie du serveur (8 kHz) normalisée à 24 kHz", wav_info(out)[2] == 24000, str(wav_info(out)))
_requests.clear()
asyncio.run(tts.synthesise("x", "male_0"))
check("voix non mappée -> voix par défaut", _requests[0]["body"]["voice"] == "af_x")
try:
    asyncio.run(tts.synthesise("x", "narrator", reference_audio_path="ref.wav"))
    check("clonage non supporté -> erreur claire", False)
except Exception as exc:  # noqa: BLE001
    check("clonage non supporté -> erreur claire", "clonage" in str(exc))
tts_b = get_tts_provider(settings, override="openai_tts", options={"model": "autre", "base_url": BASE})
_requests.clear()
asyncio.run(tts_b.synthesise("x", "narrator"))
check("option à chaud `model` du TTS prioritaire", _requests[0]["body"]["model"] == "autre")

print("\n[4] TTS « commande externe »")
script = _TMP / "fake_tts.py"
script.write_text(textwrap.dedent('''
    import sys, wave
    text = open(sys.argv[1], encoding="utf-8").read()
    out, voice = sys.argv[2], sys.argv[3]
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\\x00\\x00" * (16000 * (2 if voice == "long" else 1)))
    open(out + ".seen", "w", encoding="utf-8").write(text + "|" + voice)
'''))
os.environ["TTS_COMMAND"] = f'"{sys.executable}" "{script}" {{text_file}} {{out}} {{voice}}'
os.environ["TTS_COMMAND_VOICE_MAP"] = json.dumps({"narrator": "long", "default": "court"})
get_settings.cache_clear()
settings = get_settings()
cmd = get_tts_provider(settings, override="command")
w1 = asyncio.run(cmd.synthesise("Bonjour; rm -rf / && echo $(whoami) `id`", "narrator"))
from app.services.audio.format import wav_duration_ms  # noqa: E402
check("commande exécutée, sortie normalisée à 24 kHz", wav_info(w1)[2] == 24000)
check("voix mappée transmise (long = 2 s)", abs(wav_duration_ms(w1) - 2000) < 30, str(wav_duration_ms(w1)))
w2 = asyncio.run(cmd.synthesise("x", "male_0"))
check("voix par défaut (court = 1 s)", abs(wav_duration_ms(w2) - 1000) < 30)
script2 = _TMP / "fail_tts.py"
script2.write_text("import sys\nsys.stderr.write('modèle introuvable')\nsys.exit(3)\n")
os.environ["TTS_COMMAND"] = f'"{sys.executable}" "{script2}"'
get_settings.cache_clear()
try:
    asyncio.run(get_tts_provider(get_settings(), override="command").synthesise("x", "narrator"))
    check("code de sortie != 0 -> TTSError", False)
except Exception as exc:  # noqa: BLE001
    check("code de sortie != 0 -> TTSError avec stderr", "3" in str(exc) and "modèle introuvable" in str(exc), str(exc))
script3 = _TMP / "stdout_tts.py"
script3.write_text(textwrap.dedent('''
    import sys, wave, io
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\\x00\\x00" * 12000)
    sys.stdout.buffer.write(b.getvalue())
'''))
os.environ["TTS_COMMAND"] = f'"{sys.executable}" "{script3}"'
get_settings.cache_clear()
w3 = asyncio.run(get_tts_provider(get_settings(), override="command").synthesise("x", "narrator"))
check("sans {out} : audio lu sur la sortie standard", abs(wav_duration_ms(w3) - 500) < 30)
os.environ.pop("TTS_COMMAND")
os.environ["TTS_PROVIDER"] = "edgetts"
get_settings.cache_clear()
settings = get_settings()

print("\n[5] réglages à chaud via l'API /settings")
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
import app.models  # noqa: E402,F401
from app.core import db as dbmod  # noqa: E402

eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SQLModel.metadata.create_all(eng)
dbmod._engine = eng
from app.main import app  # noqa: E402
client = TestClient(app)

r = client.get("/settings")
check("GET /settings liste providers officiels + plugins",
      r.status_code == 200 and "tone" in r.json()["available_tts_providers"]
      and "echo" in r.json()["available_llm_providers"], r.text[:300])
check("erreurs de plugin visibles", any("broken" in e["file"] for e in r.json()["plugin_errors"]))
r = client.patch("/settings", json={"preferred_llm_provider": "openai_compatible",
                                    "llm_options": {"model": "qwen3.8-27b-Q3", "base_url": BASE}})
check("PATCH modèle LLM + provider", r.status_code == 200, r.text)
check("modèle effectif = réglage à chaud (n'importe quel nom accepté)",
      r.json()["effective_llm_model"] == "qwen3.8-27b-Q3" and r.json()["llm_options"]["base_url"] == BASE)
r = client.patch("/settings", json={"preferred_tts_provider": "tone", "tts_options": {"model": "modele-inconnu-xyz"}})
check("plugin TTS comme provider préféré", r.status_code == 200 and r.json()["preferred_tts_provider"] == "tone", r.text)
check("modèle TTS quelconque accepté", r.json()["effective_tts_model"] == "modele-inconnu-xyz")
r = client.patch("/settings", json={"tts_options": {"command": "rm -rf /"}})
check("clé non autorisée (command) refusée en 422", r.status_code == 422, r.text)
r = client.patch("/settings", json={"llm_options": {"base_url": "file:///etc/passwd"}})
check("base_url non http(s) refusée", r.status_code == 422)
r = client.patch("/settings", json={"preferred_llm_provider": "nexistepas"})
check("provider inconnu refusé (422)", r.status_code == 422)
r = client.patch("/settings", json={"llm_options": {}})
check("{} efface les réglages à chaud", r.status_code == 200 and r.json()["llm_options"] == {})
r = client.patch("/settings", json={"preferred_tts_provider": None, "preferred_llm_provider": None})
check("provider préféré effaçable", r.status_code == 200 and r.json()["preferred_llm_provider"] is None)

print("\n[6] liste des modèles proposés")
r = client.get("/settings/models", params={"kind": "llm", "provider": "openai_compatible"})
check("modèles du serveur OpenAI listés", r.json()["models"] == ["llama-x", "qwen3.8-27b"], r.text)
r = client.get("/settings/models", params={"kind": "llm", "provider": "ollama"})
check("Ollama injoignable -> 200 + error, jamais 500", r.status_code == 200 and r.json()["models"] == [] and r.json()["error"], r.text)
r = client.get("/settings/models", params={"kind": "tts", "provider": "tone"})
check("suggestions d'un plugin", r.json()["models"] == ["tone-a", "tone-b"])
r = client.get("/settings/models", params={"kind": "tts", "provider": "qwen"})
check("raccourcis Qwen proposés", "1.7b" in r.json()["models"])
check("kind invalide -> 422", client.get("/settings/models", params={"kind": "x"}).status_code == 422)

print("\n[7] sondes d'état")
st = client.get("/settings/status").json()
check("statut LLM/TTS présents", "llm" in st and "tts" in st)
client.patch("/settings", json={"preferred_llm_provider": "openai_compatible",
                                "llm_options": {"model": "qwen3.8-27b", "base_url": BASE}})
st = client.get("/settings/status").json()
check("sonde OpenAI : modèle présent -> ok", st["llm"]["status"] == "ok", str(st["llm"]))
client.patch("/settings", json={"llm_options": {"model": "absent", "base_url": BASE}})
check("sonde OpenAI : modèle absent -> warning", client.get("/settings/status").json()["llm"]["status"] == "warning")
client.patch("/settings", json={"preferred_tts_provider": "qwen"})
st = client.get("/settings/status").json()
check("sonde Qwen : paquets manquants -> error explicite (torch non chargé dans l'API)",
      st["tts"]["status"] == "error" and "torch" in st["tts"]["detail"], str(st["tts"]))
check("sonde TTS suit la préférence (et non le .env)", "Qwen" in st["tts"]["name"])
client.patch("/settings", json={"preferred_tts_provider": None, "preferred_llm_provider": None, "llm_options": {}, "tts_options": {}})

print("\n[8] options transmises aux providers officiels")
from app.services.llm.ollama import OllamaProvider  # noqa: E402
o = OllamaProvider(settings, {"model": "qwen3.8:27b", "base_url": "http://autre:11434"})
check("Ollama : modèle et hôte à chaud", o._model == "qwen3.8:27b" and o._base_url == "http://autre:11434")
captured = {}
async def _fake_chat(**kw):
    captured.update(kw)
    class _R:
        class message:
            content = json.dumps({"characters": [], "attributions": []})
    return _R()
o._client.chat = _fake_chat
asyncio.run(o.analyze("Un texte."))
check("Ollama : schéma JSON transmis à `format`", isinstance(captured["format"], dict) and "attributions" in captured["format"]["properties"])
check("Ollama : température basse", captured["options"]["temperature"] == 0.2)
check("Ollama : raisonnement coupé", captured["think"] is False)

from app.services.tts.qwen import QwenTTSProvider  # noqa: E402
q1 = QwenTTSProvider(settings, options={"model": "0.6b"})
check("Qwen : raccourci 0.6b", q1._model_id.endswith("0.6B-CustomVoice") and q1._base_model_id.endswith("0.6B-Base"))
q2 = QwenTTSProvider(settings, options={"model": "MonOrg/mon-checkpoint", "base_model": "MonOrg/mon-base"})
check("Qwen : checkpoint libre (identifiant Hugging Face)", q2._model_id == "MonOrg/mon-checkpoint" and q2._base_model_id == "MonOrg/mon-base")
os.environ["QWEN_VOICE_MAP"] = json.dumps({"narrator": "MaVoix"})
get_settings.cache_clear()
q3 = QwenTTSProvider(get_settings())
check("Qwen : table de voix surchargeable (QWEN_VOICE_MAP)", q3.resolve_voice("narrator") == "MaVoix" and q3.resolve_voice("male_0") == "Dylan")
os.environ.pop("QWEN_VOICE_MAP")
get_settings.cache_clear()
settings = get_settings()

print("\n[9] EdgeTTS : voix dédoublonnées et surchargeables")
from app.services.tts.edgetts import EdgeTTSProvider  # noqa: E402
from app.services.voice_assignment import NARRATOR_VOICE_ID, list_catalogue_voices  # noqa: E402
for locale in ("fr-FR", "en-US"):
    prov = EdgeTTSProvider(settings, options={"locale": locale})
    ids = [v for v, _ in list_catalogue_voices()]
    voices = {v: prov.resolve_voice(v) for v in ids}
    others = [n for v, n in voices.items() if v != NARRATOR_VOICE_ID]
    check(f"{locale} : aucun personnage n'a la voix du narrateur", voices[NARRATOR_VOICE_ID] not in others, str(voices))
    check(f"{locale} : toutes les voix de personnages sont distinctes", len(set(others)) == len(others), str(voices))
os.environ["EDGETTS_VOICE_MAP"] = json.dumps({"male_1": "fr-CA-JeanNeural", "narrator": {"voice": "fr-FR-HenriNeural", "rate": "-5%"}})
get_settings.cache_clear()
pe = EdgeTTSProvider(get_settings(), options={"locale": "fr-FR"})
check("EDGETTS_VOICE_MAP : surcharge d'une voix", pe.resolve_voice("male_1") == "fr-CA-JeanNeural")
check("EDGETTS_VOICE_MAP : forme détaillée (voix + débit)", pe._entry("narrator") == ("fr-FR-HenriNeural", None, "-5%"))
os.environ.pop("EDGETTS_VOICE_MAP")
get_settings.cache_clear()

print("\n[10] worker : options à chaud + cache des modèles lourds")
from sqlmodel import Session  # noqa: E402
from app.models import AppSetting, Book  # noqa: E402
from app.workers import tasks  # noqa: E402
check("options JSON invalides -> {}", tasks._parse_options("{pas du json") == {} and tasks._parse_options("[1]") == {} and tasks._parse_options(None) == {})
with Session(eng) as s:
    row = s.get(AppSetting, 1) or AppSetting(id=1)
    row.tts_options = json.dumps({"model": "0.6b"})
    row.preferred_tts_provider = "qwen"
    row.llm_options = json.dumps({"model": "x"})
    s.add(row)
    b = Book(title="t", source_path="x", language="fr"); s.add(b); s.commit(); s.refresh(b)
    tasks._release_all_tts()
    prov = tasks._get_tts_provider(settings, s, b)
    check("le worker applique les réglages TTS à chaud", isinstance(prov, QwenTTSProvider) and prov._model_id.endswith("0.6B-CustomVoice"))
    prov2 = tasks._get_tts_provider(settings, s, b)
    check("provider à modèle lourd réutilisé (cache)", prov is prov2)
    prov._model = object()
    check("déchargement sur demande", tasks._release_all_tts() == 1 and prov._model is None)
    check("options LLM lues par le worker", tasks._llm_options(s) == {"model": "x"})

print()
_server.shutdown()
if _errors:
    print(f"{len(_errors)} échec(s)")
    sys.exit(1)
print("Tous les tests OK")
