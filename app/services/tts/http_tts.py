"""Provider TTS pour tout serveur exposant `POST {base}/audio/speech` (API OpenAI Audio).

Couvre les serveurs locaux qui imitent cette API (Kokoro-FastAPI, openedai-speech, serveurs
Chatterbox/Fish/… avec une couche compatible) comme les services cloud qui la proposent : un
nouveau moteur s'ajoute donc SANS code, uniquement par configuration.

Configuration (.env, tout est aussi modifiable à chaud pour base_url et model dans Paramètres) :
  TTS_HTTP_BASE_URL      ex. http://localhost:8880/v1
  TTS_HTTP_MODEL         ex. kokoro
  TTS_HTTP_API_KEY       facultatif
  TTS_HTTP_VOICE_MAP     JSON {"narrator": "ff_siwis", "male_0": "am_adam", ..., "default": "ff_siwis"}
  TTS_HTTP_EXTRA_BODY    JSON fusionné dans chaque requête (ex. {"speed": 0.95, "lang": "fr"})
  TTS_HTTP_EMOTION_FIELD nom du champ du corps où envoyer l'émotion de la réplique (facultatif)
  TTS_HTTP_CONCURRENCY   requêtes simultanées (1 par défaut ; monter pour un serveur cloud)
"""
import httpx

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.audio.format import normalize_audio
from app.services.tts.base import BaseTTSProvider


def _dict_setting(settings, name: str) -> dict:
    value = getattr(settings, name, None)
    return value if isinstance(value, dict) else {}


class OpenAICompatibleTTSProvider(BaseTTSProvider):
    max_chars = 1000

    def __init__(self, settings: Settings, options: dict | None = None,
                 language: str | None = None) -> None:
        options = options or {}
        self._base_url = str(options.get("base_url") or settings.tts_http_base_url).rstrip("/")
        self._model = options.get("model") or settings.tts_http_model
        self._api_key = settings.tts_http_api_key
        self._voice_map = _dict_setting(settings, "tts_http_voice_map")
        self._extra_body = _dict_setting(settings, "tts_http_extra_body")
        self._emotion_field = settings.tts_http_emotion_field
        self._language = language
        self.supports_concurrency = max(1, int(settings.tts_http_concurrency))

    def resolve_voice(self, voice_id: str) -> str:
        return str(self._voice_map.get(voice_id) or self._voice_map.get("default") or voice_id)

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        if reference_audio_path is not None:
            raise TTSError(
                f"openai_tts:{voice_id}",
                NotImplementedError(
                    "Le provider openai_tts ne gère pas le clonage de voix "
                    "(utiliser Qwen, ou un plugin dédié : docs/PLUGINS.md)."
                ),
            )
        body = {
            "model": self._model,
            "input": text,
            "voice": self.resolve_voice(voice_id),
            "response_format": "wav",
            **self._extra_body,
        }
        if emotion and self._emotion_field:
            body[self._emotion_field] = emotion
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0)) as client:
                r = await client.post(f"{self._base_url}/audio/speech", headers=headers, json=body)
                r.raise_for_status()
                return normalize_audio(r.content)
        except Exception as exc:
            raise TTSError(f"openai_tts:{voice_id}", exc)


def list_tts_http_voices(base_url: str, api_key: str | None, timeout: float = 5.0) -> list[str]:
    """Voix annoncées par le serveur, si il expose GET /audio/voices (extension courante)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = httpx.get(f"{base_url.rstrip('/')}/audio/voices", headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    voices = data.get("voices", data) if isinstance(data, dict) else data
    return sorted(str(v.get("id", v.get("name", v))) if isinstance(v, dict) else str(v) for v in voices)
