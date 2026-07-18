"""check_phase37.py — Phase 37 : câblage de AppSetting.preferred_tts_provider.

Contexte : la préférence globale était éditable en Paramètres (PATCH /settings)
mais jamais lue par le pipeline de génération, qui restait figé sur
Settings.tts_provider (.env). app.workers.tasks._effective_tts_provider() insère
désormais ce maillon entre l'override par livre (Book.tts_provider, prioritaire)
et le défaut usine (Settings.tts_provider, utilisé en dernier recours).

Valide :
  - book_tts_provider défini -> toujours prioritaire, préférence globale ignorée.
  - book_tts_provider absent + préférence globale définie -> préférence globale.
  - book_tts_provider absent + pas de préférence globale -> None (les appelants
    retombent eux-mêmes sur Settings.tts_provider, comportement inchangé).
  - _synthesise_chapter_worker utilise bien _effective_tts_provider (vérifié
    par patch + capture d'arguments, même approche que check_phase36.py).
    Le point d'appel d'assign_voices (analyze_book) réutilise la même fonction
    _effective_tts_provider déjà couverte en [2] -- non re-testé en bout en
    bout ici car _analyze_book_impl s'appuie sur get_engine() (moteur global
    mis en cache), pas un engine injectable comme _synthesise_chapter_worker.

Run: .venv/Scripts/python tests/check_phase37.py
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
    "DATABASE_URL": "sqlite:///./scriptvox_test_p37.db",
    "HUEY_DB_PATH": "./huey_test_p37.db",
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
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.models import AppSetting, Book, Chapter  # noqa: E402
from app.workers.tasks import _effective_tts_provider  # noqa: E402
ok("_effective_tts_provider, AppSetting, Book, Chapter")

get_settings.cache_clear()


def _make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


# ── 2. Résolution directe de _effective_tts_provider ─────────────────────────
section("_effective_tts_provider : override livre > préférence globale > None")

_e2 = _make_test_engine()
with Session(_e2) as _sess:
    check("pas de préférence globale, pas d'override -> None",
          _effective_tts_provider(_sess, None) is None)

    _sess.add(AppSetting(id=1, preferred_tts_provider="qwen"))
    _sess.commit()
    check("préférence globale='qwen', pas d'override -> 'qwen'",
          _effective_tts_provider(_sess, None) == "qwen")
    check("override livre='edgetts' prime sur la préférence globale",
          _effective_tts_provider(_sess, "edgetts") == "edgetts")


# ── 3. _synthesise_chapter_worker utilise la préférence globale ─────────────
section("_synthesise_chapter_worker transmet la préférence globale à get_tts_provider")

_e3 = _make_test_engine()
with Session(_e3) as _sess:
    _sess.add(AppSetting(id=1, preferred_tts_provider="qwen"))
    _book3 = Book(title="B3", source_path="/tmp/b3.epub", tts_provider=None)
    _sess.add(_book3)
    _sess.commit()
    _sess.refresh(_book3)
    _ch3 = Chapter(book_id=_book3.id, position=1, title="Ch1", raw_text="Bonjour.")
    _sess.add(_ch3)
    _sess.commit()
    _ch3_id = _ch3.id

_captured_kwargs: dict = {}


def _fake_get_tts_provider(settings, override=None, language=None):
    _captured_kwargs["override"] = override
    return MagicMock()


with patch("app.services.tts.factory.get_tts_provider", side_effect=_fake_get_tts_provider), \
     patch("app.services.audio.chapter._synthesise_segments", new=AsyncMock(return_value=(b"", []))), \
     patch("app.workers.tasks._release_qwen_gpu"):
    import asyncio  # noqa: E402
    from app.workers.tasks import _synthesise_chapter_worker  # noqa: E402
    asyncio.run(_synthesise_chapter_worker(_ch3_id, _e3))

check("override='qwen' (préférence globale, book.tts_provider=None) transmis à get_tts_provider",
      _captured_kwargs.get("override") == "qwen", f"got {_captured_kwargs}")


# ── Nettoyage fichiers de test résiduels ──────────────────────────────────────
for _leftover in ("scriptvox_test_p37.db", "huey_test_p37.db"):
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
