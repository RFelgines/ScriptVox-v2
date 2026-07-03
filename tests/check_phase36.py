"""check_phase36.py — Phase 36 : locale TTS par livre (étape 2 du chantier i18n).

Contexte : étape 1 (Phase 34) a paramétré la segmentation LLM par langue via
Book.language. Cette étape fait la même chose côté TTS : EdgeTTSProvider et
QwenTTSProvider résolvaient jusqu'ici leur locale/langue UNIQUEMENT depuis la
config globale (EDGETTS_LOCALE / QWEN_LANGUAGE), quel que soit le livre en
cours de synthèse. Ils acceptent maintenant un paramètre optionnel `language`
(valeur brute de Book.language), résolu via le même `resolve_profile` que la
segmentation (code "en"/"fr" -> locale). Fallback sur la config globale si
`language` est absent/vide (zéro régression sur les livres déjà traités).

Valide :
  - EdgeTTSProvider(settings, language=...) résout en-US / fr-FR selon le
    profil ; sans `language`, retombe sur settings.edgetts_locale (inchangé).
  - QwenTTSProvider(settings, language=...) résout English / French selon le
    profil ; sans `language`, retombe sur settings.qwen_language (inchangé).
  - get_tts_provider(settings, override=..., language=...) propage `language`
    à EdgeTTS/Qwen mais pas à Piper (mono-langue local, pas concerné).
  - _synthesise_chapter_worker (app/workers/tasks.py) transmet book.language
    à get_tts_provider().

Run: .venv/Scripts/python tests/check_phase36.py
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
    "EDGETTS_LOCALE": "fr-FR",
    "QWEN_LANGUAGE": "French",
    "DATABASE_URL": "sqlite:///./scriptvox_test_p36.db",
    "HUEY_DB_PATH": "./huey_test_p36.db",
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
from app.config import Settings, get_settings  # noqa: E402
from app.services.tts.edgetts import EdgeTTSProvider  # noqa: E402
from app.services.tts.factory import get_tts_provider  # noqa: E402
from app.services.tts.qwen import QwenTTSProvider  # noqa: E402
ok("EdgeTTSProvider, QwenTTSProvider, get_tts_provider")

get_settings.cache_clear()
_settings = Settings()


# ── 2. EdgeTTSProvider : résolution de locale par langue ─────────────────────
section("EdgeTTSProvider(language=...) résout en-US / fr-FR")
check("language='en' -> en-US", EdgeTTSProvider(_settings, language="en")._locale == "en-US")
check("language='en-US' -> en-US", EdgeTTSProvider(_settings, language="en-US")._locale == "en-US")
check("language='fr-FR' -> fr-FR", EdgeTTSProvider(_settings, language="fr-FR")._locale == "fr-FR")
check("language=None -> fallback settings.edgetts_locale (fr-FR)",
      EdgeTTSProvider(_settings, language=None)._locale == "fr-FR")
check("language='' -> fallback settings.edgetts_locale (fr-FR)",
      EdgeTTSProvider(_settings, language="")._locale == "fr-FR")
check("sans argument -> comportement inchangé (fr-FR)",
      EdgeTTSProvider(_settings)._locale == "fr-FR")


# ── 3. QwenTTSProvider : résolution de langue ─────────────────────────────────
section("QwenTTSProvider(language=...) résout English / French")
check("language='en' -> English", QwenTTSProvider(_settings, language="en")._language == "English")
check("language='eng' -> English", QwenTTSProvider(_settings, language="eng")._language == "English")
check("language='fr' -> French", QwenTTSProvider(_settings, language="fr")._language == "French")
check("language=None -> fallback settings.qwen_language (French)",
      QwenTTSProvider(_settings, language=None)._language == "French")
check("sans argument -> comportement inchangé (French)",
      QwenTTSProvider(_settings)._language == "French")


# ── 4. get_tts_provider : propagation du paramètre language ──────────────────
section("get_tts_provider(language=...) propage à EdgeTTS/Qwen, pas à Piper")
_p_edge = get_tts_provider(_settings, override="edgetts", language="en-US")
check("edgetts override + language='en-US' -> locale en-US", _p_edge._locale == "en-US")

_p_qwen = get_tts_provider(_settings, override="qwen", language="en-US")
check("qwen override + language='en-US' -> language English", _p_qwen._language == "English")

_p_edge_none = get_tts_provider(_settings, override="edgetts")
check("edgetts sans language -> fallback global (fr-FR)", _p_edge_none._locale == "fr-FR")


# ── 5. _synthesise_chapter_worker transmet book.language ─────────────────────
section("_synthesise_chapter_worker transmet Book.language à get_tts_provider")
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.models import Book, Chapter  # noqa: E402
from app.workers.tasks import _synthesise_chapter_worker  # noqa: E402


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


_e5 = _make_test_engine()
with Session(_e5) as _sess:
    _book5 = Book(title="EN Book", source_path="/tmp/x.epub", language="en-US")
    _sess.add(_book5)
    _sess.commit()
    _sess.refresh(_book5)
    _ch5 = Chapter(book_id=_book5.id, position=1, title="Ch1", raw_text="Hello world.")
    _sess.add(_ch5)
    _sess.commit()
    _ch5_id = _ch5.id

_fake_provider = MagicMock()
_captured_kwargs: dict = {}


def _fake_get_tts_provider(settings, override=None, language=None):
    _captured_kwargs["override"] = override
    _captured_kwargs["language"] = language
    return _fake_provider


with patch("app.services.tts.factory.get_tts_provider", side_effect=_fake_get_tts_provider), \
     patch("app.services.audio.chapter._synthesise_segments", new=AsyncMock(return_value=(b"", []))), \
     patch("app.workers.tasks._release_qwen_gpu"):
    import asyncio  # noqa: E402
    asyncio.run(_synthesise_chapter_worker(_ch5_id, _e5))

check("language='en-US' (Book.language) transmis à get_tts_provider",
      _captured_kwargs.get("language") == "en-US", f"got {_captured_kwargs}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p36.db", "huey_test_p36.db"):
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
