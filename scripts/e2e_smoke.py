"""Test de bout en bout HORS LIGNE avec de vrais processus : API (uvicorn) + worker (Huey) +
upload d'un vrai EPUB, avec un faux serveur LLM (API OpenAI) et un plugin TTS de test.

Vérifie tout le chemin : upload -> analyse -> casting -> génération par la file de chapitres ->
assemblage WAV/MP3/M4B -> téléchargement, plus l'aperçu de voix, l'arrêt et les réglages à chaud.
Aucun réseau externe, aucun GPU. Usage : python scripts/e2e_smoke.py   (code 0 = tout est bon)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="sv_e2e_"))
errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("    ok  " if cond else "    FAIL  ") + label + ("" if cond else f" -- {detail}"))
    if not cond:
        errors.append(label)


# ── faux serveur LLM : attribue chaque réplique à « Alice » ──────────────────────────────
class LLM(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "fake-model"}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n))
        user = req["messages"][-1]["content"]
        idx = [int(l[1:l.index("]")]) for l in user.splitlines() if l.startswith("[") and "[DIALOGUE]" in l]
        if "Characters detected" in user:
            content = json.dumps({"merges": []})
        else:
            content = json.dumps({
                "characters": [{"name": "Alice", "gender": "FEMALE", "age_category": "ADULT"}],
                "attributions": [{"index": i, "character_name": "Alice", "emotion": "calm"} for i in idx],
            })
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 0), LLM)
threading.Thread(target=srv.serve_forever, daemon=True).start()
LLM_URL = f"http://127.0.0.1:{srv.server_address[1]}/v1"

# ── plugin TTS de test (silence de 300 ms par appel) ─────────────────────────────────────
plug = TMP / "plugins" / "tts"
plug.mkdir(parents=True)
(plug / "beep.py").write_text(textwrap.dedent('''
    from app.services.audio.format import silence_wav
    from app.services.tts.base import BaseTTSProvider
    PROVIDER_NAME = "beep"
    class Beep(BaseTTSProvider):
        async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
            return silence_wav(300)
    def create(settings, options, language=None):
        return Beep()
'''))

# ── vrai EPUB : couverture, 2 chapitres réels avec dialogues ─────────────────────────────
from ebooklib import epub  # noqa: E402

book = epub.EpubBook()
book.set_identifier("e2e"); book.set_title("Livre de test"); book.set_language("fr"); book.add_author("Auteur")
items = []
cover = epub.EpubHtml(title="Couverture", file_name="cover.xhtml"); cover.content = "<html><body><p>Couv</p></body></html>"
book.add_item(cover); items.append(cover)
para = "".join(f"<p>« Bonjour {i} », dit Alice. La rue était calme ce soir-là et le vent tombait.</p>" for i in range(90))
for n in (1, 2):
    c = epub.EpubHtml(title=f"Chapitre {n}", file_name=f"ch{n}.xhtml")
    c.content = f"<html><body><h1>Chapitre {n}</h1>{para}</body></html>"
    book.add_item(c); items.append(c)
book.toc = tuple(items); book.add_item(epub.EpubNcx()); book.spine = items
epub_path = TMP / "test.epub"
epub.write_epub(str(epub_path), book)

env = dict(
    os.environ, LLM_PROVIDER="openai_compatible", OPENAI_BASE_URL=LLM_URL, OPENAI_MODEL="fake-model",
    TTS_PROVIDER="beep", PLUGINS_DIR=str(TMP / "plugins"),
    DATABASE_URL=f"sqlite:///{TMP}/app.db", HUEY_DB_PATH=str(TMP / "huey.db"), DATA_DIR=str(TMP / "data"),
    AUDIO_NORMALIZE="false", AUDIO_PAUSE_CHAPTER_MS="500", PYTHONPATH=str(ROOT),
    NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
)
PORT = 8791
API = f"http://127.0.0.1:{PORT}"
procs = [
    subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
                     cwd=ROOT, env=env, stdout=(TMP / "api.log").open("w"), stderr=subprocess.STDOUT),
    subprocess.Popen([sys.executable, "-m", "huey.bin.huey_consumer", "app.workers.tasks.huey", "-k", "thread", "-w", "1"],
                     cwd=ROOT, env=env, stdout=(TMP / "worker.log").open("w"), stderr=subprocess.STDOUT),
]


def wait_for(fn, timeout=120, every=0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    return None


try:
    with httpx.Client(base_url=API, timeout=30, trust_env=False) as c:
        def _settings():
            try:
                r = c.get("/settings")
                return r if r.status_code == 200 else None
            except httpx.HTTPError:
                return None

        up = wait_for(_settings, 60)
        check("API répond", up is not None)
        s = up.json() if up else {}
        check("plugin TTS chargé dans le registre", "beep" in s.get("available_tts_providers", []), str(s.get("available_tts_providers")))

        with epub_path.open("rb") as fh:
            r = c.post("/books", files={"file": ("test.epub", fh, "application/epub+zip")})
        check("upload EPUB -> 202", r.status_code == 202, r.text)
        bid = r.json()["id"]
        b = wait_for(lambda: (lambda x: x if x["status"] in ("ANALYZED", "FAILED") else None)(c.get(f"/books/{bid}").json()), 120)
        check("analyse terminée (ANALYZED)", b and b["status"] == "ANALYZED", str(b and (b["status"], b["error_message"])))
        chs = c.get(f"/books/{bid}/chapters").json()
        check("3 chapitres importés, la couverture exclue", [x["included"] for x in chs] == [False, True, True], str(chs))
        chars = c.get(f"/books/{bid}/characters").json()
        check("personnage Alice détecté avec une voix", any(x["name"] == "Alice" and x["voice_id"] for x in chars), str(chars))

        # aperçu de voix (tâche courte prioritaire)
        alice = next(x for x in chars if x["name"] == "Alice")
        r = c.post(f"/characters/{alice['id']}/preview", json={"voice_id": alice["voice_id"]})
        check("aperçu de voix demandé (202)", r.status_code == 202, r.text)
        ok = wait_for(lambda: c.get(f"/characters/{alice['id']}/preview", params={"voice_id": alice["voice_id"]}).status_code == 200, 60)
        check("aperçu de voix généré par le worker", bool(ok))

        # génération du livre par la file de chapitres
        r = c.post(f"/books/{bid}/generate")
        check("génération lancée (202)", r.status_code == 202, r.text)
        seen_stage = set()

        def done():
            x = c.get(f"/books/{bid}").json()
            seen_stage.add(x["stage"])
            return x if x["status"] in ("DONE", "FAILED") else None

        b = wait_for(done, 180)
        check("livre DONE", b and b["status"] == "DONE", str(b and (b["status"], b["error_message"])))
        if b and b["status"] == "DONE":
            chs = c.get(f"/books/{bid}/chapters").json()
            check("chapitres inclus DONE avec durée", all(x["status"] == "DONE" and x["duration_ms"] for x in chs if x["included"]), str(chs))
            mp3 = c.get(f"/books/{bid}/audio/mp3")
            check("MP3 téléchargeable", mp3.status_code == 200 and len(mp3.content) > 1000, str(mp3.status_code))
            if shutil.which("ffmpeg"):
                m4b = c.get(f"/books/{bid}/audio/m4b")
                check("M4B téléchargeable", m4b.status_code == 200 and len(m4b.content) > 1000, str(m4b.status_code))
            wav = c.get(f"/books/{bid}/audio")
            check("WAV téléchargeable", wav.status_code == 200 and wav.content[:4] == b"RIFF")
            seg = c.get(f"/books/{bid}/chapters/2/segments").json()
            check("timeline de segments disponible", len(seg) > 10 and seg[1]["audio_offset_ms"] > seg[0]["audio_offset_ms"], str(seg[:2]))

        # régénération d'un chapitre terminé (bug corrigé : ne faisait rien)
        r = c.post(f"/books/{bid}/chapters/2/generate")
        check("régénération d'un chapitre DONE acceptée", r.status_code == 202, r.text)
        ch2 = wait_for(lambda: (lambda x: x if x["status"] == "DONE" and x["priority"] == 0 else None)(
            c.get(f"/books/{bid}/chapters").json()[2]) and not any(
            x["status"] in ("PENDING", "GENERATING") for x in c.get(f"/books/{bid}/chapters").json() if x["included"]), 60)
        check("le chapitre régénéré repasse DONE (la file se vide)", bool(ch2))

        # réglages à chaud
        r = c.patch("/settings", json={"preferred_llm_provider": "openai_compatible", "llm_options": {"model": "fake-model", "base_url": LLM_URL}})
        check("réglages LLM à chaud", r.status_code == 200 and r.json()["effective_llm_model"] == "fake-model", r.text)
        st = c.get("/settings/status", params={"deep": "true"}).json()
        check("sonde du serveur LLM : ok", st["llm"]["status"] == "ok", str(st["llm"]))
        # garde cross-site
        r = c.post(f"/books/{bid}/stop", headers={"Origin": "https://evil.example"})
        check("écriture cross-site refusée", r.status_code == 403)
        check("suppression du livre", c.delete(f"/books/{bid}").status_code == 204)
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    srv.shutdown()
    if errors:
        for name in ("api.log", "worker.log"):
            print(f"\n--- {name} (fin) ---")
            print("\n".join((TMP / name).read_text(errors="replace").splitlines()[-25:]))

print()
if errors:
    print(f"{len(errors)} échec(s) ; traces dans {TMP}")
    sys.exit(1)
shutil.rmtree(TMP, ignore_errors=True)
print("Test de bout en bout OK")
