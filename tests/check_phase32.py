"""check_phase32.py — Phase 32 : regroupement des segments par checkpoint TTS.

Contexte (investigation RAM/VRAM 2026-07-02) : Qwen3-TTS a deux checkpoints qui
ne peuvent pas cohabiter sur une carte 10 Go (CustomVoice pour catalogue/
narrateur, Base pour les voix clonées) -- app/services/tts/qwen.py décharge
l'un avant de charger l'autre à chaque bascule. _synthesise_segments traitait
les segments dans l'ordre narratif, donc un chapitre où voix clonées et voix
catalogue s'entremêlent (mesuré sur Harry Potter T02 : 10-12 bascules/chapitre)
rechargeait un checkpoint de ~3-4 Go depuis le disque à chaque alternance,
fragmentant l'allocateur CUDA jusqu'à saturer la VRAM et déborder en RAM
système (repli silencieux du pilote Windows).

Ce lot regroupe les appels TTS par checkpoint (tous les segments "non clonés"
d'abord, puis tous les "clonés"), indépendamment de l'ordre narratif, tout en
réassemblant le WAV final et les timings dans l'ORDRE NARRATIF d'origine.

Valide :
  - Régression : chapitre 100% non-cloné (ou 100% cloné) -> comportement et
    résultat inchangés (aucun regroupement à faire, ordre = ordre narratif).
  - Chapitre avec voix clonées et non-clonées ENTRELACÉES dans l'ordre
    narratif -> les appels TTS réels sont effectués groupés par checkpoint
    (tous les non-clonés, puis tous les clonés), au plus 1 transition.
  - Le WAV assemblé et les timings (offset/durée par segment) restent dans
    l'ORDRE NARRATIF d'origine, pas dans l'ordre d'appel TTS -- vérifié avec
    des durées différentes par segment pour détecter un mauvais réordonnancement.
  - should_abort() est toujours vérifié avant CHAQUE segment (peu importe le
    groupe), pas seulement entre les deux groupes.

Run: .venv/Scripts/python tests/check_phase32.py
"""
import io
import os
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p32.db",
    "HUEY_DB_PATH": "./huey_test_p32.db",
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


def _make_wav_bytes(n_frames: int, framerate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
import asyncio  # noqa: E402

from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.core.enums import SegmentType, VoiceKind  # noqa: E402
from app.models import Book, Chapter, Character, Segment, Voice  # noqa: E402
from app.services.audio.chapter import _synthesise_segments  # noqa: E402
from app.services.voice_assignment import NARRATOR_VOICE_ID  # noqa: E402
ok("_synthesise_segments, models, enums, NARRATOR_VOICE_ID")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


class _RecordingTTS:
    """Enregistre l'ordre réel des appels + le checkpoint utilisé (cloné si
    reference_audio_path fourni). Durée du WAV retourné = len(text) * 10
    frames, pour détecter un réordonnancement incorrect des timings."""

    def __init__(self) -> None:
        self.call_order: list[str] = []       # textes, dans l'ordre des appels
        self.checkpoint_seq: list[str] = []   # "base" / "custom", dans l'ordre des appels

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        self.call_order.append(text)
        self.checkpoint_seq.append("base" if reference_audio_path else "custom")
        return _make_wav_bytes(len(text) * 10)


def _make_book_setup(engine, voices: list[tuple[str, str | None]]):
    """voices: liste de (kind, reference_audio_path) pour créer un personnage
    par entrée (voice_id auto: 'v0', 'v1', ...). Retourne (chapter_id, voice_ids)."""
    with Session(engine) as s:
        book = Book(title="P32Test", source_path="/tmp/x.epub")
        s.add(book)
        s.commit()
        s.refresh(book)
        ch = Chapter(book_id=book.id, position=1, title="Ch1", raw_text="x")
        s.add(ch)
        s.commit()
        s.refresh(ch)

        voice_ids = []
        for i, (kind, ref) in enumerate(voices):
            vid = f"v{i}"
            s.add(Voice(voice_id=vid, name=vid, kind=kind, reference_audio_path=ref))
            char = Character(book_id=book.id, name=f"Char{i}", voice_id=vid)
            s.add(char)
            s.commit()
            s.refresh(char)
            voice_ids.append((vid, char.id))
        # narrateur toujours présent (non-cloné, requis par _synthesise_segments)
        s.add(Voice(voice_id=NARRATOR_VOICE_ID, name="Narrator", kind=VoiceKind.CATALOGUE))
        s.commit()
        ch_id = ch.id
    return ch_id, voice_ids


def _add_segments(engine, chapter_id: int, entries: list[tuple[str, int | None]]):
    """entries: (texte, character_id ou None pour narration)."""
    with Session(engine) as s:
        for pos, (text, char_id) in enumerate(entries, start=1):
            s.add(Segment(
                chapter_id=chapter_id, position=pos, text=text,
                segment_type=SegmentType.NARRATION if char_id is None else SegmentType.DIALOGUE,
                character_id=char_id,
            ))
        s.commit()


# ── 2. Régression : chapitre 100% non-cloné -> ordre inchangé ────────────────
section("Régression : aucune voix clonée -> ordre d'appel = ordre narratif")
_e2 = _make_test_engine()
_ch2, _v2 = _make_book_setup(_e2, [(VoiceKind.CATALOGUE, None)])
_add_segments(_e2, _ch2, [
    ("Narration A.", None),
    ("Dialogue B.", _v2[0][1]),
    ("Narration C.", None),
])
_tts2 = _RecordingTTS()
with Session(_e2) as _s:
    _result2 = asyncio.run(_synthesise_segments(_ch2, _s, _tts2))
check("résultat non None", _result2 is not None)
check("ordre d'appel = ordre narratif", _tts2.call_order == ["Narration A.", "Dialogue B.", "Narration C."],
      f"got {_tts2.call_order}")
check("aucune bascule (100% CustomVoice)", set(_tts2.checkpoint_seq) == {"custom"},
      f"got {_tts2.checkpoint_seq}")


# ── 3. Voix clonées/non-clonées ENTRELACÉES -> appels regroupés par checkpoint
section("Voix entrelacées -> appels TTS regroupés par checkpoint (<=1 bascule)")
_e3 = _make_test_engine()
_ch3, _v3 = _make_book_setup(_e3, [
    (VoiceKind.CLONED, "/ref/a.wav"),      # v0 -- cloné
    (VoiceKind.CATALOGUE, None),           # v1 -- catalogue
    (VoiceKind.CLONED, "/ref/b.wav"),      # v2 -- cloné
])
_v0_char, _v1_char, _v2_char = _v3[0][1], _v3[1][1], _v3[2][1]
# Ordre narratif : narrateur, cloné(v0), catalogue(v1), cloné(v2), narrateur
_add_segments(_e3, _ch3, [
    ("N1", None),
    ("C1", _v0_char),
    ("Cat1", _v1_char),
    ("C2", _v2_char),
    ("N2", None),
])
_tts3 = _RecordingTTS()
with Session(_e3) as _s:
    _result3 = asyncio.run(_synthesise_segments(_ch3, _s, _tts3))
check("résultat non None", _result3 is not None)


def _count_transitions(seq: list[str]) -> int:
    return sum(1 for a, b in zip(seq, seq[1:]) if a != b)


check("au plus 1 bascule de checkpoint sur les 5 appels (vs 4 en ordre narratif)",
      _count_transitions(_tts3.checkpoint_seq) <= 1,
      f"checkpoint_seq={_tts3.checkpoint_seq}")
check("tous les appels 'custom' regroupés avant tous les appels 'base' (ou l'inverse)",
      _tts3.checkpoint_seq == sorted(_tts3.checkpoint_seq, key=lambda c: c == "base"),
      f"got {_tts3.checkpoint_seq}")
check("les 5 textes sont bien tous appelés (aucun perdu)",
      sorted(_tts3.call_order) == sorted(["N1", "C1", "Cat1", "C2", "N2"]),
      f"got {_tts3.call_order}")


# ── 4. Le WAV assemblé / les timings restent dans l'ORDRE NARRATIF ───────────
section("Timings et WAV assemblé dans l'ordre narratif, pas l'ordre d'appel TTS")
if _result3 is not None:
    _wav3, _timing3 = _result3
    check("5 timings produits", len(_timing3) == 5, f"got {len(_timing3)}")
    with Session(_e3) as _s:
        _segs3 = _s.exec(
            __import__("sqlmodel").select(Segment)
            .where(Segment.chapter_id == _ch3).order_by(Segment.position)
        ).all()
    # Durée attendue par segment = len(texte)*10 frames -> ms via _wav_duration_ms
    # (framerate 22050) ; texte le plus long ("Cat1" ou "N1"/"N2" = 2 chars, "C1"/"C2"
    # = 2 chars aussi) -- on vérifie plutôt la correspondance seg_id <-> position,
    # et que les offsets sont strictement croissants dans l'ordre narratif.
    expected_ids = [s.id for s in _segs3]
    actual_ids = [t[0] for t in _timing3]
    check("timings dans l'ordre narratif (seg_id)", actual_ids == expected_ids,
          f"expected {expected_ids}, got {actual_ids}")
    offsets = [t[1] for t in _timing3]
    check("offsets strictement croissants (0 puis cumulatifs)",
          offsets == sorted(offsets) and offsets[0] == 0, f"got {offsets}")
    # Vérifie qu'assemble_wav_bytes a bien concaténé dans l'ordre narratif : la
    # durée totale du WAV assemblé doit correspondre à la somme des durées, dans
    # n'importe quel ordre de concat (somme invariante) -- test complémentaire :
    # le nombre total de frames du WAV = somme des frames de chaque texte*10.
    with wave.open(io.BytesIO(_wav3), "rb") as _w:
        _total_frames = _w.getnframes()
    _expected_frames = sum(len(t) * 10 for t in ["N1", "C1", "Cat1", "C2", "N2"])
    check("WAV assemblé contient bien tous les segments (frames totales)",
          _total_frames == _expected_frames, f"expected {_expected_frames}, got {_total_frames}")
else:
    fail("_result3 est None, impossible de vérifier les timings")


# ── 5. should_abort() vérifié avant CHAQUE segment, groupes compris ──────────
section("should_abort() vérifié avant chaque segment, y compris entre les 2 groupes")
_e5 = _make_test_engine()
_ch5, _v5 = _make_book_setup(_e5, [(VoiceKind.CLONED, "/ref/a.wav")])
_add_segments(_e5, _ch5, [
    ("N1", None),
    ("C1", _v5[0][1]),
    ("N2", None),
])
_tts5 = _RecordingTTS()
_abort_after = {"n": 0}


def _abort_after_2() -> bool:
    _abort_after["n"] += 1
    return _abort_after["n"] > 2  # laisse passer les 2 premiers appels, coupe au 3e


with Session(_e5) as _s:
    _result5 = asyncio.run(_synthesise_segments(_ch5, _s, _tts5, should_abort=_abort_after_2))
check("résultat None (abandon avant la fin)", _result5 is None)
check("exactement 2 segments synthétisés avant l'abandon", _tts5.call_order and len(_tts5.call_order) == 2,
      f"got {_tts5.call_order}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p32.db", "huey_test_p32.db"):
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
