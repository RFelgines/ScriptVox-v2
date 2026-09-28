"""Registre des providers LLM et TTS : officiels + plugins déposés par l'utilisateur.

Objectif : changer de moteur (ou en ajouter un que le projet ne connaît pas) sans toucher au
code de l'application.

Trois niveaux, du plus simple au plus libre :
  1. **Officiel** — un nom de provider (`ollama`, `gemini`, `openai_compatible`, `edgetts`,
     `piper`, `qwen`, `openai_tts`, `command`) + un modèle éditable à chaud dans Paramètres.
  2. **Générique** — `openai_compatible` (LLM) et `openai_tts` (TTS) parlent à n'importe quel
     serveur exposant l'API OpenAI (LM Studio, llama.cpp, vLLM, OpenRouter, Kokoro-FastAPI…) ;
     `command` lance un programme externe de l'utilisateur.
  3. **Plugin** — un fichier Python déposé dans `plugins/llm/` ou `plugins/tts/` (dossier
     configurable via PLUGINS_DIR). Voir docs/PLUGINS.md.

Contrat d'un plugin (module Python, nom de fichier ne commençant pas par `_`) :
    PROVIDER_NAME = "mon_moteur"                       # obligatoire, [a-z0-9_]+
    def create(settings, options) -> provider          # obligatoire
    DESCRIPTION = "texte affiché dans Paramètres"      # facultatif
    def list_models(settings, options) -> list[str]    # facultatif (suggestions dans l'UI)
`options` est le dict des réglages à chaud (model, base_url…) sauvegardés en base.
"""
import importlib.util
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_NAME_RE = re.compile(r"^[a-z0-9_]+$")

# Fabriques : (settings, options) -> provider. Les imports sont paresseux pour ne pas charger
# torch/google/ollama tant que le provider n'est pas réellement demandé.


def _llm_ollama(settings, options):
    from app.services.llm.ollama import OllamaProvider
    return OllamaProvider(settings, options)


def _llm_gemini(settings, options):
    from app.services.llm.gemini import GeminiProvider
    return GeminiProvider(settings, options)


def _llm_openai_compatible(settings, options):
    from app.services.llm.openai_compatible import OpenAICompatibleProvider
    return OpenAICompatibleProvider(settings, options)


def _tts_edgetts(settings, options, language=None):
    from app.services.tts.edgetts import EdgeTTSProvider
    return EdgeTTSProvider(settings, language=language, options=options)


def _tts_piper(settings, options, language=None):
    from app.services.tts.piper import PiperProvider
    return PiperProvider(settings)


def _tts_qwen(settings, options, language=None):
    from app.services.tts.qwen import QwenTTSProvider
    return QwenTTSProvider(settings, language=language, options=options)


def _tts_openai(settings, options, language=None):
    from app.services.tts.http_tts import OpenAICompatibleTTSProvider
    return OpenAICompatibleTTSProvider(settings, options, language)


def _tts_omnivoice(settings, options, language=None):
    from app.services.tts.omnivoice import OmniVoiceTTSProvider
    return OmniVoiceTTSProvider(settings, options, language)


def _tts_command(settings, options, language=None):
    from app.services.tts.command import CommandTTSProvider
    return CommandTTSProvider(settings, options, language)


# name -> (factory, description)
BUILTIN_LLM: dict[str, tuple[Callable, str]] = {
    "ollama": (_llm_ollama, "Ollama (local) — n'importe quel modèle installé"),
    "gemini": (_llm_gemini, "Google Gemini (cloud)"),
    "openai_compatible": (
        _llm_openai_compatible,
        "Serveur compatible OpenAI (LM Studio, llama.cpp, vLLM, OpenRouter…)",
    ),
}
BUILTIN_TTS: dict[str, tuple[Callable, str]] = {
    "edgetts": (_tts_edgetts, "EdgeTTS (cloud gratuit)"),
    "piper": (_tts_piper, "Piper (local, CPU)"),
    "qwen": (_tts_qwen, "Qwen3-TTS (local, GPU) — n'importe quel checkpoint compatible"),
    "openai_tts": (
        _tts_openai,
        "Serveur TTS compatible OpenAI (/v1/audio/speech : Kokoro-FastAPI, openedai-speech…)",
    ),
    "omnivoice": (
        _tts_omnivoice,
        "OmniVoice (local, GPU) — voix conçues et clonées, 600+ langues ; "
        "serveur scripts/omnivoice_server.py ; poids CC-BY-NC : usage non commercial",
    ),
    "command": (_tts_command, "Programme externe (commande définie dans .env)"),
}

_plugins_loaded_for: str | None = None
_plugin_llm: dict[str, dict[str, Any]] = {}
_plugin_tts: dict[str, dict[str, Any]] = {}
_plugin_errors: list[dict[str, str]] = []


def plugins_dir() -> Path:
    raw = os.environ.get("PLUGINS_DIR", "").strip()
    if not raw:
        return _PROJECT_ROOT / "plugins"
    p = Path(raw)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _load_module(path: Path, kind: str):
    spec = importlib.util.spec_from_file_location(f"scriptvox_plugin_{kind}_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"impossible de charger {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plugins(force: bool = False) -> None:
    """Charge (une fois par valeur de PLUGINS_DIR) les plugins. Un plugin défaillant est
    ignoré et son erreur mémorisée (visible dans Paramètres) : jamais bloquant pour l'appli."""
    global _plugins_loaded_for
    root = plugins_dir()
    key = str(root)
    if _plugins_loaded_for == key and not force:
        return
    _plugin_llm.clear()
    _plugin_tts.clear()
    _plugin_errors.clear()
    _plugins_loaded_for = key
    for kind, store, builtin in (("llm", _plugin_llm, BUILTIN_LLM), ("tts", _plugin_tts, BUILTIN_TTS)):
        folder = root / kind
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                module = _load_module(path, kind)
                name = getattr(module, "PROVIDER_NAME", None)
                create = getattr(module, "create", None)
                if not isinstance(name, str) or not _NAME_RE.match(name):
                    raise ValueError("PROVIDER_NAME manquant ou invalide (attendu : [a-z0-9_]+)")
                if not callable(create):
                    raise ValueError("fonction create(settings, options) manquante")
                if name in builtin:
                    raise ValueError(f"le nom {name!r} est déjà pris par un provider officiel")
                store[name] = {
                    "create": create,
                    "description": getattr(module, "DESCRIPTION", "") or f"Plugin ({path.name})",
                    "list_models": getattr(module, "list_models", None),
                    "file": str(path),
                }
                logger.info("plugin %s chargé : %s (%s)", kind, name, path.name)
            except Exception as exc:  # noqa: BLE001 — un plugin cassé ne doit jamais casser l'appli
                logger.warning("plugin %s ignoré (%s) : %s", kind, path.name, exc)
                _plugin_errors.append({"file": str(path.relative_to(root)), "error": str(exc)})


def llm_provider_names() -> list[str]:
    load_plugins()
    return sorted(set(BUILTIN_LLM) | set(_plugin_llm))


def tts_provider_names() -> list[str]:
    load_plugins()
    return sorted(set(BUILTIN_TTS) | set(_plugin_tts))


def provider_descriptions(kind: str) -> dict[str, str]:
    load_plugins()
    builtin, plugins = (BUILTIN_LLM, _plugin_llm) if kind == "llm" else (BUILTIN_TTS, _plugin_tts)
    out = {n: d for n, (_, d) in builtin.items()}
    out.update({n: p["description"] for n, p in plugins.items()})
    return out


def plugin_errors() -> list[dict[str, str]]:
    load_plugins()
    return list(_plugin_errors)


def build_llm_provider(name: str, settings, options: dict | None):
    load_plugins()
    options = options or {}
    if name in BUILTIN_LLM:
        return BUILTIN_LLM[name][0](settings, options)
    if name in _plugin_llm:
        return _plugin_llm[name]["create"](settings, options)
    raise ValueError(f"Unknown llm_provider {name!r}. Accepted values: {llm_provider_names()}")


def build_tts_provider(name: str, settings, options: dict | None, language: str | None = None):
    load_plugins()
    options = options or {}
    if name in BUILTIN_TTS:
        return BUILTIN_TTS[name][0](settings, options, language)
    if name in _plugin_tts:
        create = _plugin_tts[name]["create"]
        try:
            return create(settings, options, language=language)
        except TypeError:  # plugin qui ne déclare pas `language`
            return create(settings, options)
    raise ValueError(f"Unknown tts_provider {name!r}. Accepted values: {tts_provider_names()}")


def plugin_list_models(kind: str, name: str, settings, options: dict | None) -> list[str] | None:
    """Suggestions de modèles fournies par un plugin, ou None si le plugin n'en déclare pas."""
    load_plugins()
    store = _plugin_llm if kind == "llm" else _plugin_tts
    fn = store.get(name, {}).get("list_models")
    if fn is None:
        return None
    return list(fn(settings, options or {}))
