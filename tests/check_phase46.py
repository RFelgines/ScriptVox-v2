"""check_phase46.py — audit 2026-09-25, lot audio : format 24 kHz, pauses, découpage, concurrence,
niveau sonore, assemblage avec conversion, M4B chapitré.

Run: python tests/check_phase46.py
"""
import asyncio
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="sv_p46_")
os.environ.update({
    "LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3", "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p46.db", "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": f"{_TMP}/data", "TTS_PROVIDER": "edgetts",
    "AUDIO_PAUSE_SAME_VOICE_MS": "250", "AUDIO_PAUSE_VOICE_CHANGE_MS": "450",
    "AUDIO_NORMALIZE": "false",
})

_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    ok  {label}")
    else:
        msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


from app.services.audio import format as F  # noqa: E402
from app.services.audio.assembler import assemble_wav_from_files  # noqa: E402

print("[1] format : normalisation de n'importe quel audio")
rate = F.OUTPUT_SAMPLE_RATE
check("fréquence de sortie = 24 kHz", rate == 24000)
wav22 = F.pcm16_to_wav(b"\x10\x00" * 22050, 22050)
norm = F.normalize_audio(wav22)
check("WAV 22,05 kHz -> 24 kHz mono 16 bits", F.wav_info(norm) == (1, 2, 24000), str(F.wav_info(norm)))
check("durée conservée (~1 s)", abs(F.wav_duration_ms(norm) - 1000) < 20, str(F.wav_duration_ms(norm)))
already = F.pcm16_to_wav(b"\x00\x00" * 24000, 24000)
check("WAV déjà conforme -> renvoyé tel quel (même objet)", F.normalize_audio(already) is already)
stereo = io.BytesIO()
with wave.open(stereo, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(b"\x01\x00\x02\x00" * 44100)
check("stéréo 44,1 kHz -> mono 24 kHz", F.wav_info(F.normalize_audio(stereo.getvalue())) == (1, 2, 24000))
try:
    F.normalize_audio(b"pas de l'audio du tout")
    check("audio illisible -> ValueError", False)
except ValueError as exc:
    check("audio illisible -> ValueError explicite", "illisible" in str(exc))
if shutil.which("ffmpeg"):
    mp3 = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-f", "mp3", "-"], capture_output=True).stdout
    check("MP3 décodé -> 24 kHz mono", F.wav_info(F.normalize_audio(mp3)) == (1, 2, 24000))

print("\n[2] format : silence, niveau sonore, découpage en phrases")
check("silence de 500 ms", F.wav_duration_ms(F.silence_wav(500)) == 500)
quiet = F.pcm16_to_wav((b"\x64\x00\x9c\xff") * 6000, 24000)  # amplitude ~100
adjusted = F.adjust_level(quiet)
import numpy as np  # noqa: E402
def _rms(wavb: bytes) -> float:
    with wave.open(io.BytesIO(wavb)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    return float(np.sqrt(np.mean(a ** 2)))
check("un signal faible est remonté (gain borné à +6 dB)", 1.9 < _rms(adjusted) / _rms(quiet) <= 2.01,
      f"{_rms(adjusted) / _rms(quiet):.2f}")
silent = F.silence_wav(200)
check("un silence total reste inchangé", F.adjust_level(silent) == silent)
loud = F.pcm16_to_wav((b"\xff\x7f\x01\x80") * 6000, 24000)
check("un signal saturé ne dépasse pas le plafond", max(abs(np.frombuffer(
    wave.open(io.BytesIO(F.adjust_level(loud))).readframes(6000 * 2), dtype="<i2").astype(int))) <= 32768 * 0.9)
text = "Première phrase. Deuxième phrase plus longue ! Troisième ? Quatrième et dernière."
parts = F.split_sentences(text, 40)
check("découpe aux fins de phrase, chaque morceau <= 40", all(len(p) <= 40 for p in parts), str(parts))
check("aucun mot perdu", " ".join(parts).split() == text.split())
check("texte court -> un seul morceau", F.split_sentences("Court.", 400) == ["Court."])
long_word = F.split_sentences("a" * 100, 30)
check("mot plus long que la limite coupé net", all(len(p) <= 30 for p in long_word) and "".join(long_word) == "a" * 100)

print("\n[3] assembleur : conversion à la volée + silences entre fichiers")
d = Path(_TMP) / "asm"
d.mkdir()
(d / "a.wav").write_bytes(F.pcm16_to_wav(b"\x10\x00" * 22050, 22050))
(d / "b.wav").write_bytes(F.silence_wav(1000))
out = d / "out.wav"
assemble_wav_from_files([d / "a.wav", d / "b.wav"], out, target_rate=24000, gaps_ms=500)
with wave.open(str(out)) as w:
    dur = w.getnframes() / w.getframerate()
    check("22,05 kHz + 24 kHz assemblés à 24 kHz", w.getframerate() == 24000)
check("durée = 1 s + 0,5 s de silence + 1 s", abs(dur - 2.5) < 0.02, f"{dur}")
try:
    assemble_wav_from_files([d / "a.wav", d / "b.wav"], d / "strict.wav")
    check("sans target_rate le garde-fou de format reste strict", False)
except ValueError:
    check("sans target_rate le garde-fou de format reste strict", True)

print("\n[4] synthèse de chapitre : pauses, offsets, découpage, concurrence")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.enums import SegmentType  # noqa: E402
from app.models import Book, Chapter, Character, Segment  # noqa: E402
from app.services.audio import chapter as chapter_mod  # noqa: E402
from app.services.tts.base import BaseTTSProvider  # noqa: E402


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


class _Stub(BaseTTSProvider):
    def __init__(self, conc=1, max_chars=500, delay=0.0):
        self.supports_concurrency = conc
        self.max_chars = max_chars
        self.delay = delay
        self.calls: list[tuple[str, str]] = []
        self.in_flight = 0
        self.peak = 0

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(self.delay)
        self.in_flight -= 1
        self.calls.append((voice_id, text))
        return F.silence_wav(1000)  # 1 s par appel


def _make_chapter(eng, texts_voices):
    with Session(eng) as s:
        b = Book(title="t", source_path="x"); s.add(b); s.commit(); s.refresh(b)
        c = Chapter(book_id=b.id, position=1, raw_text="x"); s.add(c); s.commit(); s.refresh(c)
        ch_a = Character(book_id=b.id, name="A", voice_id="male_0"); s.add(ch_a); s.commit(); s.refresh(ch_a)
        for i, (text, is_dialogue) in enumerate(texts_voices, start=1):
            s.add(Segment(chapter_id=c.id, position=i, text=text,
                          segment_type=SegmentType.DIALOGUE if is_dialogue else SegmentType.NARRATION,
                          character_id=ch_a.id if is_dialogue else None))
        s.commit()
        return c.id


eng = _engine()
cid = _make_chapter(eng, [("Narration un.", False), ("Réplique.", True), ("Narration deux.", False)])
stub = _Stub()
with Session(eng) as s:
    wav, timing = asyncio.run(chapter_mod._synthesise_segments(cid, s, stub))
# voix : narrator, male_0, narrator -> deux changements de voix = 2 x 450 ms ; 3 x 1000 ms parlés
check("durée = 3 s + 2 x 450 ms de pause", abs(F.wav_duration_ms(wav) - 3900) < 5, str(F.wav_duration_ms(wav)))
check("offsets incluent les pauses (0, 1450, 2900)", [t[1] for t in timing] == [0, 1450, 2900], str(timing))
check("duration_ms = durée parlée seule", all(t[2] == 1000 for t in timing), str(timing))
check("l'ordre de synthèse est l'ordre narratif", [c[1] for c in stub.calls] ==
      ["Narration un.", "Réplique.", "Narration deux."])

eng2 = _engine()
cid2 = _make_chapter(eng2, [("Un.", False), ("Deux.", False)])
with Session(eng2) as s:
    wav2, t2 = asyncio.run(chapter_mod._synthesise_segments(cid2, s, _Stub()))
check("même voix : pause plus courte (250 ms)", [t[1] for t in t2] == [0, 1250], str(t2))

eng3 = _engine()
long_text = " ".join(f"Phrase numéro {i} du long texte." for i in range(40))
cid3 = _make_chapter(eng3, [(long_text, False)])
stub3 = _Stub(max_chars=200)
with Session(eng3) as s:
    wav3, t3 = asyncio.run(chapter_mod._synthesise_segments(cid3, s, stub3))
check("texte long découpé en plusieurs appels TTS", len(stub3.calls) > 3, f"{len(stub3.calls)} appels")
check("chaque appel respecte max_chars", all(len(t) <= 200 for _, t in stub3.calls))
check("aucun mot perdu par le découpage", " ".join(t for _, t in stub3.calls).split() == long_text.split())
check("un seul segment en sortie (timing)", len(t3) == 1)

eng4 = _engine()
cid4 = _make_chapter(eng4, [(f"Segment {i}.", False) for i in range(12)])
seq = _Stub(conc=1, delay=0.05)
par = _Stub(conc=6, delay=0.05)
t0 = time.monotonic()
with Session(eng4) as s:
    asyncio.run(chapter_mod._synthesise_segments(cid4, s, seq))
t_seq = time.monotonic() - t0
t0 = time.monotonic()
with Session(eng4) as s:
    _, tp = asyncio.run(chapter_mod._synthesise_segments(cid4, s, par))
t_par = time.monotonic() - t0
check("concurrence 1 : jamais plus d'un appel simultané", seq.peak == 1, str(seq.peak))
check("concurrence 6 : jusqu'à 6 appels simultanés", 2 <= par.peak <= 6, str(par.peak))
check("la concurrence accélère nettement", t_par < t_seq * 0.5, f"{t_par:.2f}s vs {t_seq:.2f}s")
check("l'ordre narratif du résultat est préservé (offsets croissants)",
      [t[1] for t in tp] == sorted(t[1] for t in tp))

aborts = {"n": 0}
def _abort_after_two():
    aborts["n"] += 1
    return aborts["n"] > 2
eng5 = _engine()
cid5 = _make_chapter(eng5, [(f"S{i}.", False) for i in range(6)])
st5 = _Stub()
with Session(eng5) as s:
    res = asyncio.run(chapter_mod._synthesise_segments(cid5, s, st5, should_abort=_abort_after_two))
check("arrêt en cours de chapitre -> None", res is None)
check("arrêt effectif (segments non synthétisés)", len(st5.calls) < 6, str(len(st5.calls)))

class _Boom(_Stub):
    async def synthesise(self, *a, **k):
        raise RuntimeError("boom")
old_delay = chapter_mod._TTS_RETRY_DELAY
chapter_mod._TTS_RETRY_DELAY = 0
eng6 = _engine()
cid6 = _make_chapter(eng6, [("A.", False), ("B.", False)])
try:
    with Session(eng6) as s:
        asyncio.run(chapter_mod._synthesise_segments(cid6, s, _Boom(conc=3)))
    check("une erreur TTS remonte", False)
except RuntimeError:
    check("une erreur TTS remonte (les autres tâches sont annulées)", True)
chapter_mod._TTS_RETRY_DELAY = old_delay

print("\n[5] un provider peut renvoyer n'importe quel format audio")
class _Mp3ish(_Stub):
    async def synthesise(self, *a, **k):
        return F.pcm16_to_wav(b"\x00\x00" * 8000, 8000)  # 1 s à 8 kHz
eng7 = _engine()
cid7 = _make_chapter(eng7, [("Bonjour.", False)])
with Session(eng7) as s:
    w7, _ = asyncio.run(chapter_mod._synthesise_segments(cid7, s, _Mp3ish()))
check("sortie provider 8 kHz normalisée à 24 kHz", F.wav_info(w7) == (1, 2, 24000))

print("\n[6] M4B : chapitres et métadonnées")
from app.services.audio import m4b  # noqa: E402
marks = m4b.chapter_marks([1000, 2000, 500], ["Un", "Deux", "Trois"], 250)
check("positions de chapitres = durées + jonctions", marks == [("Un", 0, 1000), ("Deux", 1250, 3250), ("Trois", 3500, 4000)], str(marks))
meta = m4b.build_ffmetadata("Titre; avec = spéciaux", "Auteur", marks)
check("FFMETADATA échappe = et ;", "title=Titre\; avec \\= spéciaux" in meta)
check("un bloc [CHAPTER] par chapitre", meta.count("[CHAPTER]") == 3)
if m4b.find_ffmpeg():
    src = Path(_TMP) / "book.wav"
    src.write_bytes(F.pcm16_to_wav(b"\x10\x10" * 24000 * 4, 24000))
    outm = m4b.build_m4b(src, Path(_TMP) / "book.m4b", title="T", author="A",
                         chapters=m4b.chapter_marks([1000, 3000], ["Un", "Deux"], 0))
    check("M4B produit", outm is not None and outm.exists() and outm.stat().st_size > 0)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "compact", str(outm)],
        capture_output=True, text=True).stdout
    check("2 chapitres dans le M4B", probe.count("chapter|") == 2, probe)
else:
    print("    (ffmpeg absent : test M4B ignoré)")
check("ffmpeg absent -> None sans exception",
      m4b.build_m4b(Path(_TMP) / "book.wav", Path(_TMP) / "x.m4b", title="T", author=None,
                    chapters=[], ffmpeg="/nonexistent/ffmpeg") is None)

print()
if _errors:
    print(f"{len(_errors)} échec(s)")
    sys.exit(1)
print("Tous les tests OK")
