from enum import Enum


class BookStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    ANALYZED = "ANALYZED"
    GENERATING = "GENERATING"
    DONE = "DONE"
    FAILED = "FAILED"


class SegmentType(str, Enum):
    NARRATION = "NARRATION"
    DIALOGUE = "DIALOGUE"


class ChapterStatus(str, Enum):
    PENDING    = "PENDING"
    GENERATING = "GENERATING"
    DONE       = "DONE"
    FAILED     = "FAILED"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class AgeCategory(str, Enum):
    CHILD       = "CHILD"
    YOUNG_ADULT = "YOUNG_ADULT"
    ADULT       = "ADULT"
    ELDER       = "ELDER"
    UNKNOWN     = "UNKNOWN"


class MergeSuggestionStatus(str, Enum):
    PENDING  = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
