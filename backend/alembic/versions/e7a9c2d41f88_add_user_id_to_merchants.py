"""add user_id to merchants

Revision ID: e7a9c2d41f88
Revises: 3f9e1a7c2b4d
Create Date: 2026-07-07 00:00:00.000000

Drift fix: the Merchant model (app/models/merchant.py) has a non-nullable
user_id FK to users.id (with an index), but c8758d8d5e4b created the merchants
table without it and no later migration added it.

This migration is intentionally idempotent (guarded by runtime inspection):
databases whose schema came from Base.metadata.create_all (e.g. the current
docker deployment, which is stamped at 3f9e1a7c2b4d but already has the
column) must not fail when the api container auto-runs `alembic upgrade head`
on boot.

Uses batch_alter_table so it also works on SQLite (which cannot ADD a NOT NULL
column without a default via plain ALTER). On a database that has merchant
rows but no user_id column, the NOT NULL add will fail loudly — backfill
user_id manually in that case (no sensible automatic default exists for a
per-user table).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7a9c2d41f88'
down_revision: Union[str, None] = '3f9e1a7c2b4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c['name'] for c in inspector.get_columns('merchants')}
    indexes = {i['name'] for i in inspector.get_indexes('merchants')}

    if 'user_id' not in columns:
        with op.batch_alter_table('merchants') as batch_op:
            batch_op.add_column(
                sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False)
            )
    if 'ix_merchants_user_id' not in indexes:
        op.create_index(op.f('ix_merchants_user_id'), 'merchants', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_merchants_user_id'), table_name='merchants')
    with op.batch_alter_table('merchants') as batch_op:
        batch_op.drop_column('user_id')
