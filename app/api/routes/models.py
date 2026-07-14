from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.models import (
    ModelsResponse,
    PiperVoice,
    QwenStatus,
    UnloadQwenResponse,
)

router = APIRouter()


@router.get("", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    settings = get_settings()

    piper_voices: list[PiperVoice] = []
    if settings.piper_voices_dir:
        voices_dir = Path(settings.piper_voices_dir)
        if voices_dir.is_dir():
            piper_voices = [
                PiperVoice(filename=p.name)
                for p in sorted(voices_dir.glob("*.onnx"))
            ]

    return ModelsResponse(
        piper=piper_voices,
        qwen=QwenStatus(
            model=settings.qwen_model,
            device=settings.qwen_device,
            loaded=None,
        ),
    )


@router.post("/qwen/unload", status_code=202)
def unload_qwen() -> UnloadQwenResponse:
    # Import lazy : release_qwen_vram est ajoutée dans tasks.py en Tâche 2.
    # Pattern identique à app/api/routes/voices.py:218.
    from app.workers.tasks import release_qwen_vram

    release_qwen_vram()
    return UnloadQwenResponse(
        status="queued",
        detail="Déchargement VRAM Qwen enfilé dans le worker Huey.",
    )
