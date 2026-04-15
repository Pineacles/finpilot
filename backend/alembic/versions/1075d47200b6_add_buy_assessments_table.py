"""add buy_assessments table

Revision ID: 1075d47200b6
Revises: bdebad240d79
Create Date: 2026-04-15 22:28:35.427163
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '1075d47200b6'
down_revision: Union[str, None] = 'bdebad240d79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'buy_assessments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('recommendation', sa.String(10), nullable=False),
        sa.Column('target_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('thesis', sa.String(4000), nullable=False),
        sa.Column('risk_factors', sa.String(2000), nullable=True),
        sa.Column('conviction', sa.Integer(), nullable=False),
        sa.Column('time_horizon', sa.String(10), nullable=True),
        sa.Column('assessed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_buy_assessments_user_id', 'buy_assessments', ['user_id'])
    op.create_index('ix_buy_assessments_symbol', 'buy_assessments', ['symbol'])


def downgrade() -> None:
    op.drop_index('ix_buy_assessments_symbol', table_name='buy_assessments')
    op.drop_index('ix_buy_assessments_user_id', table_name='buy_assessments')
    op.drop_table('buy_assessments')
