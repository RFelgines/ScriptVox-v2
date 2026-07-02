from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.core.enums import AgeCategory, BookStatus, ChapterStatus, Gender, MergeSuggestionStatus, SegmentType


class SegmentResponse(BaseModel):
    id: int
    position: int
    text: str
    segment_type: SegmentType
    character_id: Optional[int] = None
    character_name: Optional[str] = None   # dénormalisé depuis Character
    voice_id: Optional[str] = None         # dénormalisé depuis Character.voice_id
    audio_offset_ms: Optional[int] = None
    duration_ms: Optional[int] = None


class ChapterResponse(BaseModel):
    id: int
    position: int
    title: Optional[str] = None
    status: ChapterStatus
    error_message: Optional[str] = None
    priority: int = 0

    model_config = {"from_attributes": True}


class ChapterPriorityUpdate(BaseModel):
    priority: int


class QueueItemResponse(BaseModel):
    chapter_id: int
    book_id: int
    book_title: str
    position: int
    title: Optional[str] = None
    status: ChapterStatus
    priority: int
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
    genre: Optional[str] = None
    language: Optional[str] = None
    published_at: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BookUpdate(BaseModel):
    tts_provider: Optional[str] = None
    genre: Optional[str] = None
    language: Optional[str] = None
    published_at: Optional[date] = None
