"""add import_profiles table

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-08 00:20:00.000000

Reusable column-mapping profiles for the generic CSV importer
(services/mapped_import.py, POST /api/import/csv/{preview,mapped}).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'import_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=True),
        sa.Column('mapping', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_import_profiles_user_id'), 'import_profiles', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_import_profiles_user_id'), table_name='import_profiles')
    op.drop_table('import_profiles')
