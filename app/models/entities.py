from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.core.enums import (
    AgeCategory,
    BookStatus,
    ChapterStatus,
    Gender,
    MergeSuggestionStatus,
    SegmentType,
    VoiceKind,
)


class Book(SQLModel, table=True):
    __tablename__ = "book"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: Optional[str] = None
    source_path: str
    status: BookStatus = Field(default=BookStatus.PENDING, index=True)
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    error_message: Optional[str] = None
    # "analysis" | "generation" ; renseigné uniquement quand status=FAILED, sinon
    # None. Distingue quelle étape a échoué (l'UI proposait parfois le mauvais
    # bouton de reprise faute de cette info -- audit 2026-07-11, T2.3).
    failed_stage: Optional[str] = None
    audio_path: Optional[str] = None
    mp3_path: Optional[str] = None
    cover_path: Optional[str] = None
    tts_provider: Optional[str] = None  # None = utilise le défaut global (Settings.tts_provider)
    genre: Optional[str] = None  # texte libre, tag manuel (pas d'extraction EPUB fiable)
    language: Optional[str] = None  # auto-extrait de dc:language à l'analyse, override manuel possible
    published_at: Optional[date] = None  # tag manuel (dc:date EPUB peu fiable/absent)
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
    merge_suggestions: list["CharacterMergeSuggestion"] = Relationship(
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
    priority: int = Field(default=0)  # 0 = normal priority; higher = more urgent
    cancel_requested: bool = Field(default=False)  # set by /stop, polled by should_abort
    # Posé au dispatch réel (routes generate), effacé une fois GENERATING pris
    # en charge ou retiré -- None = jamais demandé, distinct de status=PENDING
    # seul. Lu par generate_chapter_queue_pump pour choisir le prochain
    # chapitre par priority DESC (audit 2026-07-11, Lot 3).
    queued_at: Optional[datetime] = None

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
    emotion: Optional[str] = None

    audio_offset_ms: Optional[int] = None  # position dans le WAV chapitre (ms, cumulatif)
    duration_ms: Optional[int] = None      # durée de ce segment en ms

    chapter: Optional["Chapter"] = Relationship(back_populates="segments")
    character: Optional["Character"] = Relationship(back_populates="segments")


class CharacterMergeSuggestion(SQLModel, table=True):
    __tablename__ = "character_merge_suggestion"

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    survivor_character_id: int = Field(foreign_key="character.id")
    merged_character_id: int = Field(foreign_key="character.id")
    reason: Optional[str] = None
    status: MergeSuggestionStatus = Field(default=MergeSuggestionStatus.PENDING)

    book: Optional["Book"] = Relationship(back_populates="merge_suggestions")


class Voice(SQLModel, table=True):
    __tablename__ = "voice"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Identifiant logique stable (ex. "male_0", "narrator") -- c'est CE champ que
    # Character.voice_id référence (en chaîne libre, pas de FK : préserve la
    # compatibilité avec les attributions existantes sans migration).
    voice_id: str = Field(unique=True, index=True)
    name: str
    kind: VoiceKind = Field(default=VoiceKind.CATALOGUE)
    gender: Optional[Gender] = None
    locale: Optional[str] = None
    is_favorite: bool = Field(default=False)
    # Réservé au clonage (Phase 3b, non implémenté) -- chemin de l'échantillon
    # audio de référence pour une voix CLONED.
    reference_audio_path: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_setting"

    # Table singleton (une seule ligne, id=1 toujours) -- pas de vraie clé
    # métier, juste un point d'ancrage pour des préférences app-wide qui ne
    # justifient pas encore une table dédiée par réglage.
    id: int = Field(default=1, primary_key=True)
    # Préférence globale éditable en Paramètres. Résolue par
    # app.workers.tasks._effective_tts_provider entre l'override par livre
    # (Book.tts_provider) et le défaut usine (Settings.tts_provider, .env).
    preferred_tts_provider: Optional[str] = None
    # Préférence globale éditable en Paramètres, distincte de la langue
    # d'affichage de l'UI (LanguageContext frontend). Sert de repli quand la
    # langue d'un livre n'a pas pu être détectée à l'import (dc:language EPUB
    # absent/non reconnu) -- voir app.workers.tasks._analyze_book, point
    # d'ingestion EPUB. Valeurs attendues : codes reconnus par
    # language_profiles.resolve_profile ("fr", "en").
    preferred_language: Optional[str] = None
