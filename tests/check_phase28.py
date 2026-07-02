"""check_phase28.py — Phase 28 (Lot C3, audit 2026-07-02) : retry par segment TTS.

L'analyse LLM a un retry 3x + reprise (tasks.py _analyze_book) ; la synthèse TTS
n'avait NI retry NI persistance partielle -- EdgeTTS fait un appel réseau par
segment, des milliers par roman, et un flake réseau unique faisait échouer tout
le chapitre (retour en entier : chapitres déjà DONE via C1 restent préservés,
mais celui en cours repart de zéro au prochain essai). Ce lot ajoute 3 essais
espacés autour de chaque tts.synthesise(), calqué sur le pattern LLM existant.

Valide :
  - Un segment qui échoue 2x puis réussit -> le chapitre va au bout (DONE),
    aucune erreur ne remonte.
  - Un segment qui échoue 3x -> l'exception remonte, le chapitre passe FAILED
    avec error_message renseigné (comportement inchangé du point de vue de
    l'appelant, seul le NOMBRE d'essais avant l'échec change).
  - Pas de délai perdu après le DERNIER essai (ni en cas de succès, ni en cas
    d'échec définitif) -- seulement entre les essais.
  - should_abort() reste vérifié une seule fois par segment (avant la boucle de
    retry), pas à chaque tentative -- n'interfère pas avec Lot C1.
  - Régression : happy path sans échec inchangé (retry = no-op si tout réussit
    du premier coup).

Run: .venv/Scripts/python tests/check_phase28.py
"""
import io
import os
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "LLM_PROVIDER": "ollama",
    "TTS_PROVIDER": "edgetts",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3",
    "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p28.db",
    "HUEY_DB_PATH": "./huey_test_p28.db",
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
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.core.enums import BookStatus, ChapterStatus, SegmentType  # noqa: E402
from app.core.exceptions import TTSError  # noqa: E402
from app.models import Book, Chapter, Segment  # noqa: E402
from app.services.audio.chapter import _synthesise_segments  # noqa: E402
from app.workers.tasks import _generate_chapter_impl  # noqa: E402
ok("_synthesise_segments, _generate_chapter_impl, models, enums")


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


class _FlakyTTS:
    """fail_counts: {texte: n} -- les n premiers appels pour ce texte lèvent une
    TTSError, puis les suivants réussissent (n très grand = échoue toujours)."""

    def __init__(self, fail_counts: dict[str, int] | None = None):
        self._fail_counts = fail_counts or {}
        self._seen: dict[str, int] = {}
        self.calls = 0
        self.calls_by_text: list[str] = []

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None) -> bytes:
        self.calls += 1
        self.calls_by_text.append(text)
        n = self._fail_counts.get(text, 0)
        seen = self._seen.get(text, 0)
        self._seen[text] = seen + 1
        if seen < n:
            raise TTSError(f"mock:{voice_id}", RuntimeError(f"forced failure {seen + 1}/{n}"))
        return _make_wav_bytes(50)


def _make_chapter(engine, texts: list[str]):
    with Session(engine) as s:
        book = Book(title="C3Test", source_path="/tmp/x.epub")
        s.add(book)
        s.commit()
        s.refresh(book)
        ch = Chapter(book_id=book.id, position=1, title="Ch1", raw_text="x")
        s.add(ch)
        s.commit()
        s.refresh(ch)
        for pos, text in enumerate(texts, start=1):
            s.add(Segment(
                chapter_id=ch.id, position=pos, text=text,
                segment_type=SegmentType.NARRATION, character_id=None,
            ))
        s.commit()
        ch_id = ch.id
    return ch_id


# ── 2. Régression : happy path (aucun échec) inchangé ─────────────────────────
section("Régression : segment sans échec -> synthétisé normalement, 1 seul appel")
_e2 = _make_test_engine()
_ch2 = _make_chapter(_e2, ["Un."])
_tts2 = _FlakyTTS()
with Session(_e2) as _s:
    _result2 = __import__("asyncio").run(_synthesise_segments(_ch2, _s, _tts2))
check("résultat non None", _result2 is not None)
check("1 seul appel TTS (aucun retry nécessaire)", _tts2.calls == 1, f"got {_tts2.calls}")


# ── 3. Échec 2x puis succès -> le segment finit par réussir, pas d'erreur ────
section("Segment échoue 2x puis réussit -> chapitre va au bout, sans erreur remontée")
import asyncio  # noqa: E402


async def _instant_sleep(*_a, **_kw) -> None:
    return None


_e3 = _make_test_engine()
_ch3 = _make_chapter(_e3, ["FlakySegment"])
_tts3 = _FlakyTTS(fail_counts={"FlakySegment": 2})
with patch("app.services.audio.chapter.asyncio.sleep", side_effect=_instant_sleep):
    with Session(_e3) as _s:
        _result3 = asyncio.run(_synthesise_segments(_ch3, _s, _tts3))
check("résultat non None (pas d'exception propagée)", _result3 is not None)
check("3 appels TTS au total (2 échecs + 1 succès)", _tts3.calls == 3, f"got {_tts3.calls}")
if _result3 is not None:
    _wav3, _timing3 = _result3
    check("1 timing produit malgré les 2 échecs intermédiaires", len(_timing3) == 1,
          f"got {len(_timing3)}")


# ── 4. Échec 3x -> l'exception remonte, chapitre FAILED avec error_message ───
section("Segment échoue 3x -> exception remonte, _generate_chapter_impl -> chapitre FAILED")
_e4 = _make_test_engine()
_ch4 = _make_chapter(_e4, ["AlwaysFails"])
_tts4 = _FlakyTTS(fail_counts={"AlwaysFails": 99})  # échoue toujours (jamais < 99 tentatives)

with (
    patch("app.core.db.get_engine", return_value=_e4),
    patch("app.services.tts.factory.get_tts_provider", return_value=_tts4),
    patch("app.services.audio.chapter.asyncio.sleep", side_effect=_instant_sleep),
):
    _generate_chapter_impl(_ch4)

check("3 tentatives effectuées avant abandon (pas plus, pas moins)", _tts4.calls == 3,
      f"got {_tts4.calls}")
with Session(_e4) as _s:
    _ch4_after = _s.get(Chapter, _ch4)
    check("chapitre FAILED", _ch4_after.status == ChapterStatus.FAILED,
          f"got {_ch4_after.status}")
    check("error_message renseigné", bool(_ch4_after.error_message),
          f"got {_ch4_after.error_message!r}")


# ── 5. Pas de délai après le DERNIER essai (succès ou échec définitif) ───────
section("Aucun sleep() après le dernier essai -- ni en succès (2 échecs+1) ni en échec définitif (3)")
_sleep_calls: list[float] = []


async def _counting_sleep(seconds, *a, **kw):
    _sleep_calls.append(seconds)


_e5 = _make_test_engine()
_ch5 = _make_chapter(_e5, ["FlakySuccess"])
_tts5 = _FlakyTTS(fail_counts={"FlakySuccess": 2})
_sleep_calls.clear()
with patch("app.services.audio.chapter.asyncio.sleep", side_effect=_counting_sleep):
    with Session(_e5) as _s:
        asyncio.run(_synthesise_segments(_ch5, _s, _tts5))
check("2 sleeps pour un segment qui réussit au 3e essai (après essai 1 et 2, pas après le 3e)",
      len(_sleep_calls) == 2, f"got {len(_sleep_calls)} sleeps: {_sleep_calls}")

_e5b = _make_test_engine()
_ch5b = _make_chapter(_e5b, ["AlwaysFails2"])
_tts5b = _FlakyTTS(fail_counts={"AlwaysFails2": 99})
_sleep_calls.clear()
with patch("app.services.audio.chapter.asyncio.sleep", side_effect=_counting_sleep):
    with Session(_e5b) as _s:
        try:
            asyncio.run(_synthesise_segments(_ch5b, _s, _tts5b))
            fail("Expected TTSError à propager après 3 échecs")
        except TTSError:
            pass
check("2 sleeps pour un segment qui échoue 3 fois (jamais après le 3e essai, avant de renoncer)",
      len(_sleep_calls) == 2, f"got {len(_sleep_calls)} sleeps: {_sleep_calls}")


# ── 6. should_abort() vérifié 1x par segment, pas par tentative de retry ─────
section("should_abort() vérifié une seule fois par segment (pas à chaque tentative de retry)")
_e6 = _make_test_engine()
_ch6 = _make_chapter(_e6, ["FlakySegment6"])
_tts6 = _FlakyTTS(fail_counts={"FlakySegment6": 2})
_abort_calls = {"n": 0}


def _never_abort() -> bool:
    _abort_calls["n"] += 1
    return False


with patch("app.services.audio.chapter.asyncio.sleep", side_effect=_instant_sleep):
    with Session(_e6) as _s:
        asyncio.run(_synthesise_segments(_ch6, _s, _tts6, should_abort=_never_abort))
check("should_abort() appelé 1 seule fois (pas 3, une par tentative de retry)",
      _abort_calls["n"] == 1, f"got {_abort_calls['n']}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p28.db", "huey_test_p28.db"):
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
