from typing import Optional

from pydantic import BaseModel

from app.core.enums import Gender, VoiceKind


class VoiceResponse(BaseModel):
    id: str                          # logical voice_id: "narrator", "male_0", ...
    name: str
    kind: VoiceKind = VoiceKind.CATALOGUE
    gender: Optional[Gender] = None  # MALE/FEMALE/NEUTRAL; None for "narrator"
    locale: Optional[str] = None     # provider locale (edgetts) else None
    is_favorite: bool = False

    model_config = {"from_attributes": True}


class VoiceUpdate(BaseModel):
    is_favorite: bool
