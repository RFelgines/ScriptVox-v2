"""add chapter priority and cancel_requested

Revision ID: 9e2bc226e2fa
Revises: 0a0a59b228cc
Create Date: 2026-07-02 20:08:44.678189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e2bc226e2fa'
down_revision: Union[str, Sequence[str], None] = '0a0a59b228cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default required: existing chapter rows must backfill these NOT NULL
    # columns (SQLite ADD COLUMN NOT NULL without a default fails on non-empty tables).
    op.add_column('chapter', sa.Column('priority', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('chapter', sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chapter', 'cancel_requested')
    op.drop_column('chapter', 'priority')
