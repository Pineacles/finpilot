"""drop AI analysis / trading tables

Revision ID: f3a8c91b5d2e
Revises: e7a9c2d41f88
Create Date: 2026-07-08 00:00:00.000000

Removes the AI stock-analysis and AI-trading stack: market_analyses,
post_mortems, buy_assessments, pending_orders, signal_history, tool_weights,
tool_weight_proposals. The AI analysis approach was tried and abandoned (see
README): only `symbol_classifications` (asset-type tagging) survives from
that era, plus the plain StockPosition/StockTransaction/PortfolioSnapshot
tables which were never coupled to it.

Before running this migration against a live database, archive the data with:

    python backend/scripts/export_ai_archive.py /path/to/backup.json

downgrade() recreates all seven tables exactly as they existed (columns,
indexes, constraints) so a rollback is possible, but the data itself is only
recoverable from the JSON export or a DB backup: dropping a table always
destroys its rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a8c91b5d2e'
down_revision: Union[str, None] = 'e7a9c2d41f88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Children first (FK dependents), then parents.
    op.drop_table('pending_orders')
    op.drop_index(op.f('ix_post_mortems_symbol'), table_name='post_mortems')
    op.drop_index(op.f('ix_post_mortems_user_id'), table_name='post_mortems')
    op.drop_table('post_mortems')
    op.drop_table('tool_weight_proposals')
    op.drop_index(op.f('ix_tool_weights_tool_name'), table_name='tool_weights')
    op.drop_table('tool_weights')
    op.drop_index('ix_signal_history_tool_symbol', table_name='signal_history')
    op.drop_index(op.f('ix_signal_history_run_timestamp'), table_name='signal_history')
    op.drop_index(op.f('ix_signal_history_regime'), table_name='signal_history')
    op.drop_index(op.f('ix_signal_history_symbol'), table_name='signal_history')
    op.drop_index(op.f('ix_signal_history_tool_name'), table_name='signal_history')
    op.drop_index(op.f('ix_signal_history_run_id'), table_name='signal_history')
    op.drop_table('signal_history')
    op.drop_index('ix_buy_assessments_symbol', table_name='buy_assessments')
    op.drop_index('ix_buy_assessments_user_id', table_name='buy_assessments')
    op.drop_table('buy_assessments')
    op.drop_index(op.f('ix_market_analyses_user_id'), table_name='market_analyses')
    op.drop_table('market_analyses')


def downgrade() -> None:
    op.create_table('market_analyses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('analysis_type', sa.String(length=20), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('model_used', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_analyses_user_id'), 'market_analyses', ['user_id'], unique=False)

    op.create_table('buy_assessments',
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
        sa.Column('time_stop', sa.Date(), nullable=True),
        sa.Column('assessed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_buy_assessments_user_id', 'buy_assessments', ['user_id'])
    op.create_index('ix_buy_assessments_symbol', 'buy_assessments', ['symbol'])

    op.create_table('post_mortems',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('analysis_id', sa.String(length=36), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=False),
        sa.Column('pnl_pct', sa.Float(), nullable=False),
        sa.Column('notes', sa.String(length=2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['analysis_id'], ['market_analyses.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_post_mortems_user_id'), 'post_mortems', ['user_id'], unique=False)
    op.create_index(op.f('ix_post_mortems_symbol'), 'post_mortems', ['symbol'], unique=False)

    op.create_table('pending_orders',
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

    op.create_table('signal_history',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=True),
        sa.Column('raw_output', sa.JSON(), nullable=False),
        sa.Column('signal_score', sa.Float(), nullable=True),
        sa.Column('regime', sa.String(length=30), nullable=True),
        sa.Column('regime_inputs', sa.JSON(), nullable=True),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('run_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('forward_return_1d', sa.Float(), nullable=True),
        sa.Column('forward_return_5d', sa.Float(), nullable=True),
        sa.Column('forward_return_20d', sa.Float(), nullable=True),
        sa.Column('benchmark_ticker', sa.String(length=20), nullable=True),
        sa.Column('alpha_1d', sa.Float(), nullable=True),
        sa.Column('alpha_5d', sa.Float(), nullable=True),
        sa.Column('alpha_20d', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_signal_history_run_id'), 'signal_history', ['run_id'], unique=False)
    op.create_index(op.f('ix_signal_history_tool_name'), 'signal_history', ['tool_name'], unique=False)
    op.create_index(op.f('ix_signal_history_symbol'), 'signal_history', ['symbol'], unique=False)
    op.create_index(op.f('ix_signal_history_regime'), 'signal_history', ['regime'], unique=False)
    op.create_index(op.f('ix_signal_history_run_timestamp'), 'signal_history', ['run_timestamp'], unique=False)
    op.create_index('ix_signal_history_tool_symbol', 'signal_history', ['tool_name', 'symbol'], unique=False)

    op.create_table('tool_weights',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('locked', sa.Boolean(), nullable=False),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated_by', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tool_weights_tool_name'), 'tool_weights', ['tool_name'], unique=True)

    op.create_table('tool_weight_proposals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('current_weight', sa.Float(), nullable=False),
        sa.Column('proposed_weight', sa.Float(), nullable=False),
        sa.Column('rationale', sa.String(length=2000), nullable=False),
        sa.Column('review_type', sa.String(length=20), nullable=False),
        sa.Column('review_window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('review_window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ic_30d', sa.Float(), nullable=True),
        sa.Column('ic_60d', sa.Float(), nullable=True),
        sa.Column('observations_count', sa.Integer(), nullable=False),
        sa.Column('proposed_by', sa.String(length=50), nullable=False),
        sa.Column('proposed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution', sa.String(length=20), nullable=True),
        sa.Column('resolved_by', sa.String(length=50), nullable=True),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
