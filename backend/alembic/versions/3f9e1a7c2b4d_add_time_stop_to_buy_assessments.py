"""add time_stop to buy_assessments

Revision ID: 3f9e1a7c2b4d
Revises: b2c3d4e5f6a7
Create Date: 2026-05-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3f9e1a7c2b4d'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buy_assessments', sa.Column('time_stop', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('buy_assessments', 'time_stop')
