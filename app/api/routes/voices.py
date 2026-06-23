from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.core.exceptions import TTSError
from app.schemas.voice import VoiceResponse
from app.services.tts.base import BaseTTSProvider
from app.services.tts.factory import get_tts_provider
from app.services.voice_assignment import list_catalogue_voices

router = APIRouter()

DATA_DIR = Path("data")
_SAMPLE_TEXT = "Bonjour, ceci est un aperçu de cette voix."


def get_tts_provider_dep(settings: Settings = Depends(get_settings)) -> BaseTTSProvider:
    return get_tts_provider(settings)


@router.get("", response_model=list[VoiceResponse])
def get_voices(settings: Settings = Depends(get_settings)) -> list[VoiceResponse]:
    # Only edgetts carries an intrinsic locale; piper/elevenlabs resolve voices
    # from on-disk models / remote UUIDs, so locale stays None there.
    locale = settings.edgetts_locale if settings.tts_provider == "edgetts" else None
    return [
        VoiceResponse(id=voice_id, gender=gender, locale=locale)
        for voice_id, gender in list_catalogue_voices()
    ]


@router.get("/{voice_id}/sample")
async def get_voice_sample(
    voice_id: str,
    settings: Settings = Depends(get_settings),
    provider: BaseTTSProvider = Depends(get_tts_provider_dep),
) -> FileResponse:
    valid_ids = {vid for vid, _ in list_catalogue_voices()}
    if voice_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"Unknown voice_id: {voice_id!r}")

    # Caché par (provider, voice_id) sur disque : la synthèse d'un aperçu est
    # identique à chaque appel (texte fixe) — éviter de la refaire à chaque clic,
    # surtout coûteux avec un provider lent (Qwen).
    cache_dir = DATA_DIR / "voice_samples"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{settings.tts_provider}_{voice_id}.wav"

    if not cache_path.exists():
        try:
            audio_bytes = await provider.synthesise(_SAMPLE_TEXT, voice_id)
        except TTSError as exc:
            raise HTTPException(status_code=502, detail=f"TTS sample failed: {exc}") from exc
        cache_path.write_bytes(audio_bytes)

    return FileResponse(str(cache_path), media_type="audio/wav", filename=cache_path.name)
