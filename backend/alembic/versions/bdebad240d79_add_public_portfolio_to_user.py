"""add_public_portfolio_to_user

Revision ID: bdebad240d79
Revises: c8758d8d5e4b
Create Date: 2026-04-07 21:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bdebad240d79'
down_revision: Union[str, None] = 'c8758d8d5e4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('public_share_token', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('public_portfolio', sa.Boolean(), server_default='false', nullable=False))
    op.create_index(op.f('ix_users_public_share_token'), 'users', ['public_share_token'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_public_share_token'), table_name='users')
    op.drop_column('users', 'public_portfolio')
    op.drop_column('users', 'public_share_token')
