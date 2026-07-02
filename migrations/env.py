import os
import sys
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Project root on sys.path so `import app.models` resolves regardless of the CWD
# alembic was invoked from.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Registers every SQLModel table on SQLModel.metadata (mirrors app/core/db.py's
# init_db, which does the same `import app.models` before create_all/upgrade).
import app.models  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

target_metadata = SQLModel.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL comes from the app's own .env (python-dotenv), not a value baked
# into alembic.ini — a single source of truth with app/config.py, and migrations
# always target whichever database the app itself is configured for. Only
# DATABASE_URL is required here (not the app's full fail-fast Settings): a
# migration tool shouldn't need TTS_PROVIDER/LLM_PROVIDER/etc. to run.
#
# Skipped when a URL was already set programmatically on the Config object
# (app/core/db.py's _ensure_schema does this before calling command.upgrade/
# command.stamp, to target a specific engine — e.g. a throwaway test DB).
# Without this guard, this block would silently clobber that URL with
# DATABASE_URL on every call, making _ensure_schema always migrate the app's
# main database no matter which engine it was actually invoked with.
if not config.get_main_option("sqlalchemy.url", "").strip():
    load_dotenv()
    _database_url = os.environ.get("DATABASE_URL", "").strip()
    if not _database_url:
        raise RuntimeError(
            "Missing required env var: DATABASE_URL (read from .env, same as the app)."
        )
    config.set_main_option("sqlalchemy.url", _database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
