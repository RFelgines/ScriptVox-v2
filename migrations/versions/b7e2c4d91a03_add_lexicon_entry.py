"""add lexicon_entry (lexique de prononciation)

Revision ID: b7e2c4d91a03
Revises: a1c3e5f70912
Create Date: 2026-09-28 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # ScriptVox: see db9016b64888 — generated types reference sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7e2c4d91a03'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f70912'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'lexicon_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=True),
        sa.Column('term', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('replacement', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('whole_word', sa.Boolean(), nullable=False),
        sa.Column('case_sensitive', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lexicon_entry_book_id'), 'lexicon_entry', ['book_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lexicon_entry_book_id'), table_name='lexicon_entry')
    op.drop_table('lexicon_entry')
