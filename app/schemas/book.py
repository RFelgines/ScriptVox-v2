from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.core.enums import BookStatus, ChapterStatus, Gender


class ChapterResponse(BaseModel):
    id: int
    position: int
    title: Optional[str] = None
    status: ChapterStatus
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class CharacterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    gender: Gender
    voice_tone: Optional[str] = None
    voice_id: Optional[str] = None

    model_config = {"from_attributes": True}


class BookResponse(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    status: BookStatus
    progress: float
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
