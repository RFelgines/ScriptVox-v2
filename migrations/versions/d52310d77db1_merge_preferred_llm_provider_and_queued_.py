"""merge preferred_llm_provider and queued_at heads

Revision ID: d52310d77db1
Revises: d4a16bc12e51, db9016b64888
Create Date: 2026-07-18 23:46:45.165945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # ScriptVox: autogenerate emits sqlmodel.sql.sqltypes.AutoString(...)
                 # for every String/Optional[str] column but never imports the
                 # module itself (known Alembic+SQLModel gap) — always import it
                 # here so generated migrations don't NameError on their own types.


# revision identifiers, used by Alembic.
revision: str = 'd52310d77db1'
down_revision: Union[str, Sequence[str], None] = ('d4a16bc12e51', 'db9016b64888')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
