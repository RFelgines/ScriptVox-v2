from typing import Generator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        from app.config import get_settings
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db(engine: Engine | None = None) -> None:
    import app.models  # noqa: F401 — registers all SQLModel tables with metadata
    eng = engine or get_engine()
    SQLModel.metadata.create_all(eng)

    from app.services.voice_assignment import seed_catalogue_voices
    with Session(eng) as session:
        seed_catalogue_voices(session)


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
