from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.core.enums import AgeCategory, BookStatus, ChapterStatus, Gender, MergeSuggestionStatus


class ChapterResponse(BaseModel):
    id: int
    position: int
    title: Optional[str] = None
    status: ChapterStatus
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class CharacterUpdate(BaseModel):
    voice_id: str


class CharacterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    gender: Gender
    age_category: AgeCategory = AgeCategory.UNKNOWN
    tone: Optional[str] = None
    voice_quality: Optional[str] = None
    voice_tone: Optional[str] = None
    voice_id: Optional[str] = None
    segment_count: int = 0

    model_config = {"from_attributes": True}


class MergeSuggestionResponse(BaseModel):
    id: int
    survivor_character_id: int
    merged_character_id: int
    reason: Optional[str] = None
    status: MergeSuggestionStatus

    model_config = {"from_attributes": True}


class BookResponse(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    status: BookStatus
    progress: float
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    mp3_path: Optional[str] = None
    cover_path: Optional[str] = None
    tts_provider: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BookUpdate(BaseModel):
    tts_provider: Optional[str] = None
