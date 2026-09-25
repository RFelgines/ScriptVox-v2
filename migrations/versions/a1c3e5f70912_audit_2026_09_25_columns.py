"""audit 2026-09-25: options de modèle, progression par étape, chapitres exclus, M4B

Revision ID: a1c3e5f70912
Revises: 730790d05e4d
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 — voir les autres migrations (lacune connue Alembic+SQLModel)


revision: str = 'a1c3e5f70912'
down_revision: Union[str, Sequence[str], None] = '730790d05e4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('book', sa.Column('m4b_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('book', sa.Column('stage', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('book', sa.Column('stage_progress', sa.Float(), nullable=False, server_default='0'))
    op.add_column('book', sa.Column('eta_seconds', sa.Integer(), nullable=True))
    op.add_column('chapter', sa.Column('included', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('chapter', sa.Column('duration_ms', sa.Integer(), nullable=True))
    op.add_column('voice', sa.Column('reference_text', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('app_setting', sa.Column('llm_options', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('app_setting', sa.Column('tts_options', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('app_setting') as batch:
        batch.drop_column('tts_options')
        batch.drop_column('llm_options')
    with op.batch_alter_table('voice') as batch:
        batch.drop_column('reference_text')
    with op.batch_alter_table('chapter') as batch:
        batch.drop_column('duration_ms')
        batch.drop_column('included')
    with op.batch_alter_table('book') as batch:
        batch.drop_column('eta_seconds')
        batch.drop_column('stage_progress')
        batch.drop_column('stage')
        batch.drop_column('m4b_path')
