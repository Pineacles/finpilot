"""add pending_orders table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-22 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pending_orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('account_key', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=True),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('target_order_id', sa.String(100), nullable=True),
        sa.Column('buy_sell', sa.String(4), nullable=True),
        sa.Column('amount', sa.Float, nullable=True),
        sa.Column('order_type', sa.String(20), nullable=True),
        sa.Column('duration', sa.String(20), nullable=True),
        sa.Column('limit_price', sa.Float, nullable=True),
        sa.Column('stop_price', sa.Float, nullable=True),
        sa.Column('asset_type_saxo', sa.String(10), nullable=True),
        sa.Column('mode', sa.String(10), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('buy_assessment_id', sa.String(36), sa.ForeignKey('buy_assessments.id'), nullable=True),
        sa.Column('rationale', sa.Text, nullable=True),
        sa.Column('estimated_cash_required_chf', sa.Float, nullable=True),
        sa.Column('estimated_fees_chf', sa.Float, nullable=True),
        sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('idempotency_key', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('placed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_reason', sa.Text, nullable=True),
        sa.Column('broker_order_id', sa.String(100), nullable=True),
        sa.Column('broker_response', sa.JSON, nullable=True),
    )
    op.create_index('ix_pending_orders_user_id', 'pending_orders', ['user_id'])
    op.create_index('ix_pending_orders_account_key', 'pending_orders', ['account_key'])
    op.create_index('ix_pending_orders_status', 'pending_orders', ['status'])
    op.create_index('ix_pending_orders_user_created', 'pending_orders', ['user_id', 'created_at'])
    op.create_index('ix_pending_orders_user_status', 'pending_orders', ['user_id', 'status'])
    op.create_unique_constraint(
        'uq_pending_orders_user_idempotency',
        'pending_orders',
        ['user_id', 'idempotency_key'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_pending_orders_user_idempotency', 'pending_orders', type_='unique')
    op.drop_index('ix_pending_orders_user_status', table_name='pending_orders')
    op.drop_index('ix_pending_orders_user_created', table_name='pending_orders')
    op.drop_index('ix_pending_orders_status', table_name='pending_orders')
    op.drop_index('ix_pending_orders_account_key', table_name='pending_orders')
    op.drop_index('ix_pending_orders_user_id', table_name='pending_orders')
    op.drop_table('pending_orders')
