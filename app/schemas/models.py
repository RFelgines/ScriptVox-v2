from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PiperVoice(BaseModel):
    filename: str


class QwenStatus(BaseModel):
    model: str
    device: str
    loaded: bool | None = None
    # Toujours None depuis FastAPI : l'état du checkpoint vit dans le
    # processus worker Huey (mémoire séparée — pas d'IPC disponible).


class ModelsResponse(BaseModel):
    piper: list[PiperVoice]
    qwen: QwenStatus


class UnloadQwenResponse(BaseModel):
    status: Literal["queued"]
    detail: str
