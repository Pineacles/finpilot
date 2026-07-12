"""add watchlist_items table

Revision ID: a7b8c9d0e1f2
Revises: e2f3a4b5c6d7
Create Date: 2026-07-08 09:00:00.000000

Tracking-only watchlist (selective stocks the user wants to keep an eye on,
no AI analysis/recommendations); see app.models.watchlist.WatchlistItem.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'watchlist_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'symbol', name='uq_watchlist_user_symbol'),
    )
    op.create_index(op.f('ix_watchlist_items_user_id'), 'watchlist_items', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_watchlist_items_user_id'), table_name='watchlist_items')
    op.drop_table('watchlist_items')
