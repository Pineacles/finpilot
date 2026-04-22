"""add symbol_classifications table

Revision ID: a1b2c3d4e5f6
Revises: 1075d47200b6
Create Date: 2026-04-22 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '1075d47200b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'symbol_classifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('asset_type', sa.String(20), nullable=False),
        sa.Column('source', sa.String(10), nullable=False),  # auto | user | agent
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        'ix_symbol_classifications_user_symbol',
        'symbol_classifications',
        ['user_id', 'symbol'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_symbol_classifications_user_symbol', table_name='symbol_classifications')
    op.drop_table('symbol_classifications')
