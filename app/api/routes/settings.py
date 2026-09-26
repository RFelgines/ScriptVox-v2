import importlib.util
import json
import shlex
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from app.config import Settings, get_settings
from app.core.db import get_session
from app.core.enums import VoiceKind
from app.models.entities import AppSetting, Voice
from app.services import registry
from app.services.llm.language_profiles import AVAILABLE_LANGUAGES
from app.schemas.settings import (
    ModelListResponse,
    ProviderStatus,
    SettingsResponse,
    SettingsUpdate,
    StatusResponse,
)

router = APIRouter()

# Clés acceptées dans llm_options / tts_options : rien d'exécutable ni de secret (les clés API
# restent dans .env ; TTS_COMMAND n'est jamais modifiable par l'API).
_ALLOWED_OPTION_KEYS = frozenset({"model", "base_url", "base_model", "locale"})
_MAX_OPTION_LEN = 500


def _get_or_create_app_setting(session: Session) -> AppSetting:
    row = session.get(AppSetting, 1)
    if row is None:
        row = AppSetting(id=1)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def _options_of(raw: str | None) -> dict[str, str]:
    from app.workers.tasks import _parse_options

    return {k: str(v) for k, v in _parse_options(raw).items() if k in _ALLOWED_OPTION_KEYS}


def _validate_options(name: str, options: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in options.items():
        if key not in _ALLOWED_OPTION_KEYS:
            raise HTTPException(
                status_code=422,
                detail=f"{name}: clé {key!r} non autorisée. Clés acceptées : {sorted(_ALLOWED_OPTION_KEYS)}",
            )
        value = (value or "").strip()
        if not value:
            continue  # valeur vide = « pas de surcharge »
        if len(value) > _MAX_OPTION_LEN:
            raise HTTPException(status_code=422, detail=f"{name}.{key}: valeur trop longue.")
        if key == "base_url" and not value.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail=f"{name}.base_url doit commencer par http:// ou https://")
        clean[key] = value
    return clean


def _effective_llm_model(settings: Settings, provider: str, options: dict) -> str | None:
    if options.get("model"):
        return options["model"]
    return {
        "ollama": settings.ollama_model,
        "gemini": settings.gemini_model,
        "openai_compatible": settings.openai_model,
    }.get(provider)


def _effective_tts_model(settings: Settings, provider: str, options: dict) -> str | None:
    if options.get("model"):
        return options["model"]
    return {
        "qwen": settings.qwen_model,
        "openai_tts": settings.tts_http_model,
        "edgetts": options.get("locale") or settings.edgetts_locale,
    }.get(provider)


def _settings_response(settings: Settings, row: AppSetting) -> SettingsResponse:
    llm_options = _options_of(row.llm_options)
    tts_options = _options_of(row.tts_options)
    llm = row.preferred_llm_provider or settings.llm_provider
    tts = row.preferred_tts_provider or settings.tts_provider
    return SettingsResponse(
        default_tts_provider=settings.tts_provider,
        preferred_tts_provider=row.preferred_tts_provider,
        available_tts_providers=registry.tts_provider_names(),
        preferred_language=row.preferred_language,
        available_languages=sorted(AVAILABLE_LANGUAGES),
        default_llm_provider=settings.llm_provider,
        preferred_llm_provider=row.preferred_llm_provider,
        available_llm_providers=registry.llm_provider_names(),
        llm_options=llm_options,
        tts_options=tts_options,
        effective_llm_model=_effective_llm_model(settings, llm, llm_options),
        effective_tts_model=_effective_tts_model(settings, tts, tts_options),
        llm_provider_descriptions=registry.provider_descriptions("llm"),
        tts_provider_descriptions=registry.provider_descriptions("tts"),
        plugin_errors=registry.plugin_errors(),
    )


@router.get("", response_model=SettingsResponse)
def get_app_settings(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> SettingsResponse:
    return _settings_response(settings, _get_or_create_app_setting(session))


@router.patch("", response_model=SettingsResponse)
def update_app_settings(
    payload: SettingsUpdate,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> SettingsResponse:
    # exclude_unset : un champ OMIS du body ne doit pas écraser l'autre
    # préférence avec le défaut None du schéma (même pattern que
    # patch_book/books.py) -- seul un champ explicitement envoyé (y compris
    # `null` pour effacer une préférence) est appliqué.
    fields = payload.model_dump(exclude_unset=True)
    tts_names = registry.tts_provider_names()
    llm_names = registry.llm_provider_names()
    if (
        "preferred_tts_provider" in fields
        and fields["preferred_tts_provider"] is not None
        and fields["preferred_tts_provider"] not in tts_names
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid preferred_tts_provider={fields['preferred_tts_provider']!r}. "
            f"Accepted values: {tts_names}",
        )
    if (
        "preferred_language" in fields
        and fields["preferred_language"] is not None
        and fields["preferred_language"] not in AVAILABLE_LANGUAGES
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid preferred_language={fields['preferred_language']!r}. "
            f"Accepted values: {sorted(AVAILABLE_LANGUAGES)}",
        )
    if (
        payload.preferred_llm_provider is not None
        and payload.preferred_llm_provider not in llm_names
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid preferred_llm_provider={payload.preferred_llm_provider!r}. "
            f"Accepted values: {llm_names}",
        )
    llm_options = _validate_options("llm_options", payload.llm_options) if payload.llm_options is not None else None
    tts_options = _validate_options("tts_options", payload.tts_options) if payload.tts_options is not None else None

    row = _get_or_create_app_setting(session)
    if "preferred_tts_provider" in fields:
        row.preferred_tts_provider = fields["preferred_tts_provider"]
    if "preferred_language" in fields:
        row.preferred_language = fields["preferred_language"]
    if "preferred_llm_provider" in fields:
        row.preferred_llm_provider = fields["preferred_llm_provider"]
    if llm_options is not None:
        row.llm_options = json.dumps(llm_options) if llm_options else None
    if tts_options is not None:
        row.tts_options = json.dumps(tts_options) if tts_options else None
    session.add(row)
    session.commit()
    session.refresh(row)
    return _settings_response(settings, row)


# ── Liste des modèles proposés ────────────────────────────────────────────────


@router.get("/models", response_model=ModelListResponse)
def list_available_models(
    kind: str,
    provider: str | None = None,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> ModelListResponse:
    """Suggestions de modèles pour le provider (installés localement quand le moteur sait les
    lister). Ne lève jamais : une erreur réseau est renvoyée dans `error`, la liste reste vide,
    et l'utilisateur peut de toute façon saisir n'importe quel nom à la main."""
    if kind not in ("llm", "tts"):
        raise HTTPException(status_code=422, detail="kind doit valoir 'llm' ou 'tts'.")
    row = _get_or_create_app_setting(session)
    if kind == "llm":
        name = provider or row.preferred_llm_provider or settings.llm_provider
        options = _options_of(row.llm_options)
    else:
        name = provider or row.preferred_tts_provider or settings.tts_provider
        options = _options_of(row.tts_options)
    try:
        models = _models_for(kind, name, settings, options)
        return ModelListResponse(provider=name, models=models)
    except Exception as exc:  # noqa: BLE001
        return ModelListResponse(provider=name, models=[], error=str(exc))


def _models_for(kind: str, name: str, settings: Settings, options: dict) -> list[str]:
    plugin = registry.plugin_list_models(kind, name, settings, options)
    if plugin is not None:
        return plugin
    if kind == "llm":
        if name == "ollama":
            from app.services.llm.ollama import list_ollama_models
            return list_ollama_models(options.get("base_url") or settings.ollama_base_url)
        if name == "openai_compatible":
            from app.services.llm.openai_compatible import list_openai_models
            return list_openai_models(
                options.get("base_url") or settings.openai_base_url, settings.openai_api_key,
            )
        if name == "gemini":
            from app.services.llm.gemini import list_gemini_models
            return list_gemini_models(settings.gemini_api_key)
        return []
    if name == "qwen":
        return ["1.7b", "0.6b"]
    if name == "piper" and settings.piper_voices_dir:
        return sorted(p.stem for p in Path(settings.piper_voices_dir).glob("*.onnx"))
    if name == "openai_tts":
        return [options.get("model") or settings.tts_http_model]
    if name == "edgetts":
        return ["fr-FR", "en-US"]
    return []


# ── Sondes d'état ─────────────────────────────────────────────────────────────


def _probe_llm(
    settings: Settings, provider_override: str | None = None,
    options: dict | None = None, deep: bool = False,
) -> ProviderStatus:
    options = options or {}
    effective = provider_override or settings.llm_provider
    if effective == "gemini":
        model = options.get("model") or settings.gemini_model
        name = f"Gemini ({model})"
        if not settings.gemini_api_key:
            return ProviderStatus(name=name, status="error", detail="GEMINI_API_KEY absente du .env")
        if not deep:
            return ProviderStatus(name=name, status="ok", detail="Clé API configurée (test réel : bouton « Tester »)")
        try:
            from google import genai
            genai.Client(api_key=settings.gemini_api_key).models.get(model=model)
            return ProviderStatus(name=name, status="ok", detail="Modèle accessible")
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(name=name, status="error", detail=f"Gemini : {exc}")
    if effective == "ollama":
        model = options.get("model") or settings.ollama_model
        base = options.get("base_url") or settings.ollama_base_url
        try:
            r = httpx.get(f"{base}/api/tags", timeout=2.0)
            r.raise_for_status()
            loaded = [m["name"] for m in r.json().get("models", [])]
            if any(model in name for name in loaded):
                return ProviderStatus(name=f"Ollama — {model}", status="ok", detail="Modèle chargé")
            return ProviderStatus(
                name=f"Ollama — {model}",
                status="warning",
                detail=f"Ollama répond mais le modèle '{model}' n'apparaît pas dans /api/tags",
            )
        except Exception as exc:
            return ProviderStatus(
                name=f"Ollama — {model}", status="error", detail=f"Ollama injoignable : {exc}",
            )
    if effective == "openai_compatible":
        model = options.get("model") or settings.openai_model
        base = options.get("base_url") or settings.openai_base_url
        try:
            from app.services.llm.openai_compatible import list_openai_models
            models = list_openai_models(base, settings.openai_api_key, timeout=3.0)
            if model in models:
                return ProviderStatus(name=f"Serveur OpenAI — {model}", status="ok", detail="Modèle disponible")
            return ProviderStatus(
                name=f"Serveur OpenAI — {model}", status="warning",
                detail=f"Serveur joignable ; '{model}' absent de /models ({len(models)} modèle(s) listé(s))",
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(
                name=f"Serveur OpenAI — {model}", status="error", detail=f"Serveur injoignable : {exc}",
            )
    return ProviderStatus(
        name=f"Plugin LLM — {effective}", status="ok",
        detail=registry.provider_descriptions("llm").get(effective, "Plugin chargé"),
    )


def _probe_tts(
    settings: Settings, provider_override: str | None = None,
    options: dict | None = None, deep: bool = False,
) -> ProviderStatus:
    options = options or {}
    p = provider_override or settings.tts_provider

    if p == "edgetts":
        locale = options.get("locale") or getattr(settings, "edgetts_locale", "fr-FR")
        return ProviderStatus(name=f"EdgeTTS ({locale})", status="ok", detail="Cloud, toujours disponible")

    if p == "piper":
        if not settings.piper_binary_path or not settings.piper_voices_dir:
            return ProviderStatus(name="Piper (local)", status="error",
                                  detail="PIPER_BINARY_PATH / PIPER_VOICES_DIR non définis")
        binary_ok = Path(settings.piper_binary_path).is_file()
        voices_ok = Path(settings.piper_voices_dir).is_dir()
        if binary_ok and voices_ok:
            n = len(list(Path(settings.piper_voices_dir).glob("*.onnx")))
            return ProviderStatus(
                name="Piper (local)",
                status="ok",
                detail=f"Binaire prêt · {n} modèle(s) .onnx trouvé(s)",
            )
        missing = []
        if not binary_ok:
            missing.append("binaire introuvable")
        if not voices_ok:
            missing.append("dossier voix introuvable")
        return ProviderStatus(name="Piper (local)", status="error", detail=", ".join(missing))

    if p == "qwen":
        model = options.get("model") or getattr(settings, "qwen_model", "1.7b")
        device = getattr(settings, "qwen_device", "cuda:0")
        name = f"Qwen3-TTS ({model})"
        # find_spec : ne charge PAS torch dans l'API (lourd) ; le GPU se vérifie au premier usage.
        missing = [m for m in ("torch", "qwen_tts") if importlib.util.find_spec(m) is None]
        if missing:
            return ProviderStatus(
                name=name, status="error",
                detail=f"Paquet(s) manquant(s) : {', '.join(missing)} — voir requirements-qwen.txt",
            )
        return ProviderStatus(
            name=name, status="ok",
            detail=f"Paquets installés — device {device} (GPU vérifié au premier usage)",
        )

    if p == "openai_tts":
        base = options.get("base_url") or settings.tts_http_base_url
        name = f"Serveur TTS OpenAI — {options.get('model') or settings.tts_http_model}"
        if not deep:
            return ProviderStatus(name=name, status="ok", detail=f"{base} (test réel : bouton « Tester »)")
        try:
            httpx.get(base, timeout=3.0)
            return ProviderStatus(name=name, status="ok", detail=f"{base} répond")
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(name=name, status="error", detail=f"{base} injoignable : {exc}")

    if p == "command":
        cmd = settings.tts_command or ""
        try:
            exe = shlex.split(cmd)[0] if cmd else ""
        except ValueError:
            exe = ""
        if exe and (shutil.which(exe) or Path(exe).is_file()):
            return ProviderStatus(name="Commande externe", status="ok", detail=f"Exécutable trouvé : {exe}")
        return ProviderStatus(name="Commande externe", status="error",
                              detail=f"Exécutable introuvable ({exe or 'TTS_COMMAND vide'})")

    if p in registry.tts_provider_names():
        return ProviderStatus(
            name=f"Plugin TTS — {p}", status="ok",
            detail=registry.provider_descriptions("tts").get(p, "Plugin chargé"),
        )
    return ProviderStatus(name=p, status="warning", detail="Provider inconnu")


@router.get("/status", response_model=StatusResponse)
def get_app_status(
    deep: bool = False,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> StatusResponse:
    """`deep=true` (bouton « Tester ») : appels réels aux services distants (Gemini, serveur
    TTS) ; sans, seules des vérifications locales bon marché."""
    cloned_count = session.exec(
        select(func.count()).select_from(Voice).where(Voice.kind == VoiceKind.CLONED)
    ).one()
    row = _get_or_create_app_setting(session)
    return StatusResponse(
        llm=_probe_llm(settings, row.preferred_llm_provider, _options_of(row.llm_options), deep),
        tts=_probe_tts(settings, row.preferred_tts_provider, _options_of(row.tts_options), deep),
        cloned_voices_count=cloned_count,
    )
