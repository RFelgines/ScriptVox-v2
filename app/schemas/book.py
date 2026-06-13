from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.core.enums import BookStatus


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
