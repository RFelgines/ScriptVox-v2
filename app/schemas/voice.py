from typing import Optional

from pydantic import BaseModel

from app.core.enums import Gender


class VoiceResponse(BaseModel):
    id: str                          # logical voice_id: "narrator", "male_0", ...
    gender: Optional[Gender] = None  # MALE/FEMALE/NEUTRAL; None for "narrator"
    locale: Optional[str] = None     # provider locale (edgetts) else None

    model_config = {"from_attributes": True}
