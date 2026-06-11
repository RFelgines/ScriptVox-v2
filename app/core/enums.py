from enum import Enum


class BookStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class SegmentType(str, Enum):
    NARRATION = "NARRATION"
    DIALOGUE = "DIALOGUE"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"
