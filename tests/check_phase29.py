"""check_phase29.py — Phase 29 (Lot C2, audit 2026-07-02) : encodage MP3 en flux.

Dernière limite mémoire résiduelle documentée au Lot C1 : l'assemblage WAV
(assemble_wav_from_files) était déjà disque→disque depuis C1, mais l'encodage
MP3 final (_generate_book_impl) relisait tout book.wav en RAM d'un coup
(Path.read_bytes()) puis accumulait tout le MP3 encodé avant de l'écrire — pour
un roman de ~10h (~1,6 Go de PCM), c'est exactement le pic mémoire que C1 visait
à éliminer, déplacé à cette dernière étape.

Valide :
  - wav_to_mp3_streaming produit un flux MP3 STRICTEMENT IDENTIQUE (octet pour
    octet) à l'ancien wav_to_mp3(bytes) sur la même entrée -- vérifié
    empiriquement que lameenc.Encoder.encode() appelé en plusieurs blocs alignés
    sur les échantillons produit un flux byte-identique à un appel unique
    (condition garantie par wave.readframes(), qui ne renvoie jamais une frame
    partielle).
  - Le chemin multi-blocs est réellement exercé (chunk_frames volontairement
    petit dans le test), pas juste "accidentellement correct" parce que tout
    tenait dans un seul bloc.
  - WAV plus petit qu'un bloc -> fonctionne quand même (1 seul bloc interne).
  - Mêmes erreurs de validation que wav_to_mp3 (8-bit -> ValueError, WAV vide ->
    ValueError).
  - Intégration : _generate_book_impl utilise désormais le chemin en flux de
    bout en bout (WAV assemblé depuis le disque + MP3 encodé en flux), book.mp3
    toujours produit correctement.

Pic mémoire non mesurable en test portable fiable (cf. plan) -- à vérifier au
run réel sur un livre volumineux.

Run: .venv/Scripts/python tests/check_phase29.py
"""
import io
import os
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p29.db",
    "HUEY_DB_PATH": "./huey_test_p29.db",
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


def _make_wav(n_frames: int = 5000, framerate: int = 22050, sampwidth: int = 2, tone: bool = True) -> bytes:
    """WAV avec un vrai signal (pas du silence) -- plus proche d'audio réel pour
    l'encodage MP3, évite les cas dégénérés où tout est zéro."""
    import math
    import struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        if tone and sampwidth == 2:
            samples = b"".join(
                struct.pack("<h", int(3000 * math.sin(i * 0.05))) for i in range(n_frames)
            )
            w.writeframes(samples)
        else:
            w.writeframes(b"\x00" * (n_frames * sampwidth))
    return buf.getvalue()


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
from app.services.audio.assembler import wav_to_mp3, wav_to_mp3_streaming  # noqa: E402
ok("wav_to_mp3, wav_to_mp3_streaming")


# ── 2. Flux identique octet pour octet à l'ancien wav_to_mp3(bytes) ──────────
section("wav_to_mp3_streaming produit un MP3 identique octet pour octet à wav_to_mp3(bytes)")
_wav2 = _make_wav(n_frames=5000)
_reference_mp3 = wav_to_mp3(_wav2)

with tempfile.TemporaryDirectory() as _tmp2:
    _wav_path2 = Path(_tmp2) / "in.wav"
    _wav_path2.write_bytes(_wav2)
    _mp3_path2 = Path(_tmp2) / "out.mp3"
    wav_to_mp3_streaming(_wav_path2, _mp3_path2)
    _streaming_mp3 = _mp3_path2.read_bytes()

check("même taille", len(_streaming_mp3) == len(_reference_mp3),
      f"streaming={len(_streaming_mp3)} vs référence={len(_reference_mp3)}")
check("octets strictement identiques", _streaming_mp3 == _reference_mp3)


# ── 3. Le chemin multi-blocs est réellement exercé (chunk_frames petit) ──────
section("Multi-blocs (chunk_frames petit) : toujours identique octet pour octet")
with tempfile.TemporaryDirectory() as _tmp3:
    _wav_path3 = Path(_tmp3) / "in.wav"
    _wav_path3.write_bytes(_wav2)  # même WAV que section 2 (5000 frames)
    _mp3_path3 = Path(_tmp3) / "out.mp3"
    # chunk_frames=137 sur 5000 frames -> ~37 blocs, prouve que le découpage
    # n'est pas juste "1 bloc qui contient tout par accident"
    wav_to_mp3_streaming(_wav_path3, _mp3_path3, chunk_frames=137)
    _multi_chunk_mp3 = _mp3_path3.read_bytes()
check("identique octet pour octet même avec ~37 blocs", _multi_chunk_mp3 == _reference_mp3,
      f"got {len(_multi_chunk_mp3)} bytes vs référence {len(_reference_mp3)}")


# ── 4. WAV plus petit qu'un bloc -> fonctionne quand même (1 seul bloc) ──────
section("WAV plus petit que chunk_frames -> fonctionne (1 seul bloc interne)")
_wav4 = _make_wav(n_frames=50)
_reference_mp3_small = wav_to_mp3(_wav4)
with tempfile.TemporaryDirectory() as _tmp4:
    _wav_path4 = Path(_tmp4) / "in.wav"
    _wav_path4.write_bytes(_wav4)
    _mp3_path4 = Path(_tmp4) / "out.mp3"
    wav_to_mp3_streaming(_wav_path4, _mp3_path4, chunk_frames=1_000_000)
    _small_mp3 = _mp3_path4.read_bytes()
check("identique octet pour octet (50 frames < 1 bloc de 1M)", _small_mp3 == _reference_mp3_small)


# ── 5. Régression : WAV 8-bit -> ValueError (même validation que wav_to_mp3) ──
section("Régression : WAV 8-bit -> ValueError (comme wav_to_mp3)")
_wav_8bit = _make_wav(n_frames=100, sampwidth=1, tone=False)
with tempfile.TemporaryDirectory() as _tmp5:
    _wav_path5 = Path(_tmp5) / "in.wav"
    _wav_path5.write_bytes(_wav_8bit)
    try:
        wav_to_mp3_streaming(_wav_path5, Path(_tmp5) / "out.mp3")
        fail("Expected ValueError pour un WAV 8-bit")
    except ValueError as exc:
        check("message mentionne sampwidth", "sampwidth" in str(exc), str(exc))


# ── 6. Régression : WAV vide (0 frames) -> ValueError ────────────────────────
section("Régression : WAV vide (0 frames) -> ValueError")
_wav_empty = _make_wav(n_frames=0, tone=False)
with tempfile.TemporaryDirectory() as _tmp6:
    _wav_path6 = Path(_tmp6) / "in.wav"
    _wav_path6.write_bytes(_wav_empty)
    try:
        wav_to_mp3_streaming(_wav_path6, Path(_tmp6) / "out.mp3")
        fail("Expected ValueError pour un WAV sans frames")
    except ValueError as exc:
        check("message mentionne frames", "frame" in str(exc).lower(), str(exc))


# ── 7. Intégration : _generate_book_impl utilise le chemin en flux ───────────
section("Intégration : _generate_book_impl -> book.mp3 produit via le chemin en flux")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.core.enums import BookStatus, SegmentType  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.workers.tasks import _generate_book_impl  # noqa: E402


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


_e7 = _make_test_engine()
with tempfile.TemporaryDirectory() as _tmp7:
    _src7 = str(Path(_tmp7) / "book.epub")
    with Session(_e7) as _s:
        _b7 = Book(title="C2Test", source_path=_src7, status=BookStatus.ANALYZED)
        _s.add(_b7)
        _s.commit()
        _s.refresh(_b7)
        _b7_id = _b7.id
        for _cpos in (1, 2):
            _ch7 = Chapter(book_id=_b7_id, position=_cpos, title=f"Ch{_cpos}", raw_text="x")
            _s.add(_ch7)
            _s.commit()
            _s.refresh(_ch7)
            _s.add(Segment(
                chapter_id=_ch7.id, position=1, text=f"Segment ch{_cpos}.",
                segment_type=SegmentType.NARRATION, character_id=None,
            ))
            _s.commit()

    async def _fake_synth7(text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        return _make_wav(n_frames=200)

    _tts7 = MagicMock()
    _tts7.synthesise = AsyncMock(side_effect=_fake_synth7)

    # Espionne wav_to_mp3_streaming (sans changer son comportement réel) pour
    # PROUVER que _generate_book_impl emprunte bien le nouveau chemin en flux --
    # un simple test de bon résultat final ne le prouverait pas (l'ancien
    # wav_to_mp3(bytes) produirait le même book.mp3 correct).
    from app.services.audio import assembler as _assembler_module
    _real_streaming = _assembler_module.wav_to_mp3_streaming
    _streaming_calls = {"n": 0}

    def _spy_streaming(*a, **kw):
        _streaming_calls["n"] += 1
        return _real_streaming(*a, **kw)

    with (
        patch("app.core.db.get_engine", return_value=_e7),
        patch("app.services.tts.factory.get_tts_provider", return_value=_tts7),
        patch("app.services.audio.assembler.wav_to_mp3_streaming", side_effect=_spy_streaming),
    ):
        _generate_book_impl(_b7_id)

    check("wav_to_mp3_streaming appelé exactement une fois (chemin en flux emprunté)",
          _streaming_calls["n"] == 1, f"got {_streaming_calls['n']}")

    with Session(_e7) as _s:
        _b7_after = _s.get(Book, _b7_id)
        check("livre DONE", _b7_after.status == BookStatus.DONE, f"got {_b7_after.status}")
        check("mp3_path renseigné", _b7_after.mp3_path is not None)
        if _b7_after.mp3_path:
            _mp3_bytes7 = Path(_b7_after.mp3_path).read_bytes()
            check("fichier MP3 sur disque, non vide", len(_mp3_bytes7) > 0)
            check("sync byte MP3 (0xFF) en tête", _mp3_bytes7[0] == 0xFF,
                  f"got 0x{_mp3_bytes7[0]:02X}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p29.db", "huey_test_p29.db"):
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
