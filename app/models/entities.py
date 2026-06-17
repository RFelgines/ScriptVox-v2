from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.core.enums import AgeCategory, BookStatus, ChapterStatus, Gender, SegmentType


class Book(SQLModel, table=True):
    __tablename__ = "book"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: Optional[str] = None
    source_path: str
    status: BookStatus = Field(default=BookStatus.PENDING, index=True)
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    mp3_path: Optional[str] = None
    cover_path: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    chapters: list["Chapter"] = Relationship(
        back_populates="book",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    characters: list["Character"] = Relationship(
        back_populates="book",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Chapter(SQLModel, table=True):
    __tablename__ = "chapter"
    __table_args__ = (UniqueConstraint("book_id", "position"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    position: int
    title: Optional[str] = None
    raw_text: str
    status: ChapterStatus = Field(default=ChapterStatus.PENDING)
    audio_path: Optional[str] = None
    error_message: Optional[str] = None

    book: Optional["Book"] = Relationship(back_populates="chapters")
    segments: list["Segment"] = Relationship(
        back_populates="chapter",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Character(SQLModel, table=True):
    __tablename__ = "character"
    __table_args__ = (UniqueConstraint("book_id", "name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    name: str
    description: Optional[str] = None
    gender: Gender = Field(default=Gender.UNKNOWN)
    age_category: AgeCategory = Field(default=AgeCategory.UNKNOWN)
    tone: Optional[str] = None
    voice_quality: Optional[str] = None
    voice_tone: Optional[str] = None
    voice_id: Optional[str] = None  # populated in Phase 3

    book: Optional["Book"] = Relationship(back_populates="characters")
    segments: list["Segment"] = Relationship(back_populates="character")


class Segment(SQLModel, table=True):
    __tablename__ = "segment"
    __table_args__ = (UniqueConstraint("chapter_id", "position"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    position: int
    text: str
    segment_type: SegmentType = Field(default=SegmentType.NARRATION)
    character_id: Optional[int] = Field(default=None, foreign_key="character.id", index=True)

    chapter: Optional["Chapter"] = Relationship(back_populates="segments")
    character: Optional["Character"] = Relationship(back_populates="segments")
