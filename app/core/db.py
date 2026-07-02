from pathlib import Path
from typing import Generator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

_engine: Engine | None = None
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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


def _ensure_schema(eng: Engine) -> None:
    """Bring the database schema up to date via Alembic, replacing the previous
    unconditional SQLModel.metadata.create_all() (audit 2026-07-02, Lot E /
    finding M9): a bare create_all() only ever creates MISSING tables, it never
    applies a change to an EXISTING one -- which is why every model change in
    this project's history required manually deleting scriptvox.db and losing
    the whole library.

    Self-healing for a database that predates Alembic adoption (this includes
    every scriptvox.db that already exists today, created entirely via
    create_all): if the DB already has application tables but no alembic_version
    bookkeeping table, it is STAMPED at the baseline revision instead of
    re-running "CREATE TABLE" (which would crash on tables that already exist).
    Stamping only records "this DB is already at revision X" in a new
    alembic_version table -- it never touches existing data. A brand new
    (empty) database, or one already tracked by Alembic, just runs `upgrade
    head` normally."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", eng.url.render_as_string(hide_password=False))

    existing_tables = set(inspect(eng).get_table_names())
    has_alembic_history = "alembic_version" in existing_tables
    has_app_tables = bool(existing_tables - {"alembic_version"})

    if has_app_tables and not has_alembic_history:
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def init_db(engine: Engine | None = None) -> None:
    import app.models  # noqa: F401 — registers all SQLModel tables with metadata
    eng = engine or get_engine()
    _ensure_schema(eng)

    from app.services.voice_assignment import seed_catalogue_voices
    with Session(eng) as session:
        seed_catalogue_voices(session)


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
