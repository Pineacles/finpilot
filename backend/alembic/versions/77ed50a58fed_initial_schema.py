"""initial schema

Revision ID: 77ed50a58fed
Revises:
Create Date: 2026-04-06 21:45:01.691867

NOTE: This baseline was originally committed as an empty stub (upgrade/downgrade
were both `pass`); the schema only existed via Base.metadata.create_all in
seed.py and test fixtures. It was reconstructed on 2026-07-07 from
backend/app/models/ to contain exactly the tables/columns that existed at
baseline time — i.e. everything in the models EXCEPT what later migrations in
this chain add (user_settings, merchants, categorization_log, the
public_share_token/public_portfolio columns on users, buy_assessments,
symbol_classifications, pending_orders, buy_assessments.time_stop,
merchants.user_id).

Databases whose alembic_version is already at or past this revision never
re-execute this body, so the reconstruction is safe for existing deployments.
See backend/MIGRATIONS.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '77ed50a58fed'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users (public_share_token / public_portfolio are added later by bdebad240d79) ---
    op.create_table('users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('api_key', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('base_currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)

    op.create_table('accounts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('balance', sa.Float(), nullable=True),
        sa.Column('balance_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_accounts_user_id'), 'accounts', ['user_id'], unique=False)

    op.create_table('categories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('parent_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_categories_user_id'), 'categories', ['user_id'], unique=False)

    op.create_table('transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('merchant', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('original_amount', sa.Float(), nullable=True),
        sa.Column('original_currency', sa.String(length=3), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('category_id', sa.String(length=36), nullable=True),
        sa.Column('viseca_transaction_id', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('viseca_transaction_id'),
    )
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'], unique=False)
    op.create_index(op.f('ix_transactions_date'), 'transactions', ['date'], unique=False)

    op.create_table('budgets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('category_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('period', sa.String(length=10), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_budgets_user_id'), 'budgets', ['user_id'], unique=False)

    op.create_table('savings_goals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('target_amount', sa.Float(), nullable=False),
        sa.Column('current_amount', sa.Float(), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_savings_goals_user_id'), 'savings_goals', ['user_id'], unique=False)

    op.create_table('milestones',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('target_net_worth', sa.Float(), nullable=True),
        sa.Column('target_savings', sa.Float(), nullable=True),
        sa.Column('achieved', sa.Boolean(), nullable=False),
        sa.Column('achieved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_milestones_user_id'), 'milestones', ['user_id'], unique=False)

    op.create_table('recurring_expenses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('frequency', sa.String(length=15), nullable=False),
        sa.Column('next_due_date', sa.Date(), nullable=False),
        sa.Column('category_id', sa.String(length=36), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_recurring_expenses_user_id'), 'recurring_expenses', ['user_id'], unique=False)

    op.create_table('stock_positions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('avg_cost_price', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('last_price', sa.Float(), nullable=True),
        sa.Column('last_price_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unrealized_pnl', sa.Float(), nullable=True),
        sa.Column('earnings_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_stock_positions_user_id'), 'stock_positions', ['user_id'], unique=False)
    op.create_index(op.f('ix_stock_positions_symbol'), 'stock_positions', ['symbol'], unique=False)

    op.create_table('stock_transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('fees', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_stock_transactions_user_id'), 'stock_transactions', ['user_id'], unique=False)

    op.create_table('portfolio_snapshots',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('total_cost', sa.Float(), nullable=False),
        sa.Column('total_pnl', sa.Float(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_portfolio_snapshots_user_id'), 'portfolio_snapshots', ['user_id'], unique=False)
    op.create_index(op.f('ix_portfolio_snapshots_snapshot_date'), 'portfolio_snapshots', ['snapshot_date'], unique=False)

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

    op.create_table('sync_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('records_synced', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sync_logs_user_id'), 'sync_logs', ['user_id'], unique=False)

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


def downgrade() -> None:
    # Reverse dependency order: children first.
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
    op.drop_index(op.f('ix_sync_logs_user_id'), table_name='sync_logs')
    op.drop_table('sync_logs')
    op.drop_index(op.f('ix_post_mortems_symbol'), table_name='post_mortems')
    op.drop_index(op.f('ix_post_mortems_user_id'), table_name='post_mortems')
    op.drop_table('post_mortems')
    op.drop_index(op.f('ix_market_analyses_user_id'), table_name='market_analyses')
    op.drop_table('market_analyses')
    op.drop_index(op.f('ix_portfolio_snapshots_snapshot_date'), table_name='portfolio_snapshots')
    op.drop_index(op.f('ix_portfolio_snapshots_user_id'), table_name='portfolio_snapshots')
    op.drop_table('portfolio_snapshots')
    op.drop_index(op.f('ix_stock_transactions_user_id'), table_name='stock_transactions')
    op.drop_table('stock_transactions')
    op.drop_index(op.f('ix_stock_positions_symbol'), table_name='stock_positions')
    op.drop_index(op.f('ix_stock_positions_user_id'), table_name='stock_positions')
    op.drop_table('stock_positions')
    op.drop_index(op.f('ix_recurring_expenses_user_id'), table_name='recurring_expenses')
    op.drop_table('recurring_expenses')
    op.drop_index(op.f('ix_milestones_user_id'), table_name='milestones')
    op.drop_table('milestones')
    op.drop_index(op.f('ix_savings_goals_user_id'), table_name='savings_goals')
    op.drop_table('savings_goals')
    op.drop_index(op.f('ix_budgets_user_id'), table_name='budgets')
    op.drop_table('budgets')
    op.drop_index(op.f('ix_transactions_date'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_user_id'), table_name='transactions')
    op.drop_table('transactions')
    op.drop_index(op.f('ix_categories_user_id'), table_name='categories')
    op.drop_table('categories')
    op.drop_index(op.f('ix_accounts_user_id'), table_name='accounts')
    op.drop_table('accounts')
    op.drop_index(op.f('ix_users_api_key'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
