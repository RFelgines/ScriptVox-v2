"""add preferred_language to app_setting

Revision ID: 29e226c24b2d
Revises: 9e2bc226e2fa
Create Date: 2026-07-08 07:40:05.904067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # ScriptVox: autogenerate emits sqlmodel.sql.sqltypes.AutoString(...)
                 # for every String/Optional[str] column but never imports the
                 # module itself (known Alembic+SQLModel gap) — always import it
                 # here so generated migrations don't NameError on their own types.


# revision identifiers, used by Alembic.
revision: str = '29e226c24b2d'
down_revision: Union[str, Sequence[str], None] = '9e2bc226e2fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('app_setting', sa.Column('preferred_language', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('app_setting', 'preferred_language')
