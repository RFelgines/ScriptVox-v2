"""check_phase34.py — Phase 34 : profils de langue pour la segmentation (FR/EN).

Contexte (chantier i18n, 2026-07-02) : `_pre_segment` (app/services/llm/base.py)
détectait le dialogue et son incise via des regex 100% françaises en dur
(guillemets «», inversion clitique "dit-il", verbes d'incise FR). Étape 1 du
chantier i18n : extraction dans `app/services/llm/language_profiles.py`
(FR_PROFILE + nouveau EN_PROFILE), sélectionnés via `resolve_profile(language)`
à partir de `Book.language`. Fallback FR si langue absente/non reconnue
(décision utilisateur : zéro régression sur les livres déjà traités).

Valide :
  - Régression : _pre_segment/_split_incise sans argument profile -> comportement
    FR inchangé (défaut = FR_PROFILE).
  - resolve_profile : normalisation ("en", "en-US", "eng", "English" -> EN ;
    "fr", "fr-FR", None, "" , valeur inconnue -> FR, fallback).
  - EN_PROFILE : dialogue détecté via guillemets droits/typographiques ;
    l'incise ("he shouted.", "said Harry.") tombe naturellement en narration
    SANS passer par _split_incise (incise_re=None) ; invariant byte-exact.
  - EN_PROFILE : une ligne ouverte par un tiret cadratin n'est PAS du dialogue
    (contrairement à FR_PROFILE sur le même texte) -- évite un faux positif.
  - Contrat : OllamaProvider.analyze()/GeminiProvider.analyze() acceptent le
    nouveau paramètre `language` et le propagent à resolve_profile avant
    _pre_segment.
  - _analyze_book (app/workers/tasks.py) lit Book.language une fois et le
    transmet à chaque appel provider.analyze().

Run: .venv/Scripts/python tests/check_phase34.py
"""
import os
import sys
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p34.db",
    "HUEY_DB_PATH": "./huey_test_p34.db",
    "DATA_DIR": "./data_test",
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


# ── 1. Imports ───────────────────────────────────────────────────────────────
section("Tous les modules s'importent proprement")
import asyncio  # noqa: E402

from app.services.llm.base import _pre_segment, _split_incise  # noqa: E402
from app.services.llm.language_profiles import (  # noqa: E402
    EN_PROFILE,
    FR_PROFILE,
    resolve_profile,
)
ok("_pre_segment, _split_incise, EN_PROFILE, FR_PROFILE, resolve_profile")


# ── 2. Régression : appel sans profile -> comportement FR inchangé ───────────
section("Régression : _pre_segment/_split_incise sans profile -> FR par défaut")
_s = "— Bonjour, dit Harry."
_spans = _pre_segment(_s)
check("dialogue+narration (FR par défaut)", [sp.is_dialogue for sp in _spans] == [True, False],
      f"got {[sp.is_dialogue for sp in _spans]}")
check("incise_character='Harry' (FR par défaut)", _spans[0].incise_character == "Harry",
      f"got {_spans[0].incise_character!r}")
check("_split_incise sans profile utilise FR_PROFILE explicitement",
      _split_incise(_s) == _split_incise(_s, FR_PROFILE))


# ── 3. resolve_profile : normalisation ────────────────────────────────────────
section("resolve_profile : normalisation des valeurs de Book.language")
_en_inputs = ["en", "en-US", "en-GB", "eng", "English", "ENGLISH", "  en  "]
for _val in _en_inputs:
    check(f"resolve_profile({_val!r}) -> EN_PROFILE", resolve_profile(_val) is EN_PROFILE)

_fr_fallback_inputs = [None, "", "fr", "fr-FR", "fre", "français", "de", "es", "unknown_lang"]
for _val in _fr_fallback_inputs:
    check(f"resolve_profile({_val!r}) -> FR_PROFILE (fallback)", resolve_profile(_val) is FR_PROFILE)


# ── 4. EN_PROFILE : dialogue via guillemets, incise naturellement en narration
section("EN_PROFILE : dialogue via guillemets, incise séparée sans _split_incise")
_en_text = 'Alice sat quietly. "Stop!" he shouted. Then she smiled, "said Harry."'
_en_spans = _pre_segment(_en_text, EN_PROFILE)
check("invariant byte-exact (EN)", "".join(sp.text for sp in _en_spans) == _en_text)
_en_dialogues = [sp for sp in _en_spans if sp.is_dialogue]
check("2 spans dialogue détectés (guillemets droits)", len(_en_dialogues) == 2,
      f"got {len(_en_dialogues)}")
check("aucune incise_character extraite (incise_re=None pour EN)",
      all(sp.incise_character is None for sp in _en_spans),
      f"got {[sp.incise_character for sp in _en_spans]}")
# "he shouted." doit être un span de narration séparé (pas fusionné au dialogue)
_narration_texts = [sp.text for sp in _en_spans if not sp.is_dialogue]
check("'he shouted.' présent comme narration séparée",
      any("he shouted" in t for t in _narration_texts), f"got {_narration_texts}")


# ── 5. EN_PROFILE : tiret cadratin N'EST PAS un marqueur de dialogue ─────────
section("EN_PROFILE : ligne en tiret cadratin -> narration (pas de faux positif dialogue)")
_dash_text = "— Are you coming with us tomorrow?"
_fr_dash_spans = _pre_segment(_dash_text, FR_PROFILE)
_en_dash_spans = _pre_segment(_dash_text, EN_PROFILE)
check("FR_PROFILE : tiret cadratin -> dialogue", _fr_dash_spans[0].is_dialogue is True)
check("EN_PROFILE : même texte -> narration (pas de dialogue)",
      all(not sp.is_dialogue for sp in _en_dash_spans),
      f"got {[sp.is_dialogue for sp in _en_dash_spans]}")


# ── 6. Contrat : OllamaProvider/GeminiProvider.analyze(language=...) ─────────
section("OllamaProvider.analyze(language=...) résout le profil et segmente en conséquence")
from app.config import Settings, get_settings  # noqa: E402
from app.services.llm.ollama import OllamaProvider  # noqa: E402

get_settings.cache_clear()
_settings = Settings()
_provider = OllamaProvider(_settings)


class _FakeOllamaMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeOllamaResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeOllamaMsg(content)


_captured_spans: list = []


async def _capture_chat(*_a, **kw):
    return _FakeOllamaResponse('{"characters": [], "attributions": []}')


_provider._client.chat = _capture_chat

with patch("app.services.llm.ollama._pre_segment", wraps=None) as _mock_pre_segment:
    from app.services.llm.base import _pre_segment as _real_pre_segment

    def _spy_pre_segment(text, profile=FR_PROFILE):
        _captured_spans.append(profile)
        return _real_pre_segment(text, profile)

    _mock_pre_segment.side_effect = _spy_pre_segment
    asyncio.run(_provider.analyze(_en_text, language="en-US"))
    asyncio.run(_provider.analyze(_s, language=None))

check("analyze(language='en-US') -> _pre_segment appelé avec EN_PROFILE",
      _captured_spans[0] is EN_PROFILE, f"got {_captured_spans[0]}")
check("analyze(language=None) -> _pre_segment appelé avec FR_PROFILE (fallback)",
      _captured_spans[1] is FR_PROFILE, f"got {_captured_spans[1]}")


# ── 7. _analyze_book transmet Book.language à provider.analyze() ────────────
section("_analyze_book lit Book.language une fois et le transmet à chaque appel LLM")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.models import Book, Chapter  # noqa: E402
from app.workers.tasks import _analyze_book  # noqa: E402


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


_e7 = _make_test_engine()
with Session(_e7) as _sess:
    _book7 = Book(title="EN Book", source_path="/tmp/x.epub", language="en-GB")
    _sess.add(_book7)
    _sess.commit()
    _sess.refresh(_book7)
    _ch7 = Chapter(book_id=_book7.id, position=1, title="Ch1", raw_text="Hello world.")
    _sess.add(_ch7)
    _sess.commit()
    _book7_id, _ch7_id = _book7.id, _ch7.id

from app.services.llm.base import CharacterData, LLMChapterResult  # noqa: E402

_fake_llm = MagicMock()
_fake_llm.analyze = AsyncMock(return_value=LLMChapterResult(characters=[], segments=[]))

with patch("app.services.llm.factory.get_llm_provider", return_value=_fake_llm):
    asyncio.run(_analyze_book(_book7_id, [(_ch7_id, "Hello world.")], _e7))

check("provider.analyze() appelé au moins une fois", _fake_llm.analyze.call_count >= 1)
_call_kwargs = _fake_llm.analyze.call_args
check("language='en-GB' transmis (Book.language du livre)",
      _call_kwargs.kwargs.get("language") == "en-GB", f"got {_call_kwargs.kwargs}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p34.db", "huey_test_p34.db"):
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
