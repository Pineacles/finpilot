"""add created_at to merchants

Revision ID: f4b1c2d3e4f5
Revises: a7b8c9d0e1f2
Create Date: 2026-07-08 10:00:00.000000

Nullable — existing merchant rules have no created timestamp, the merchants
page shows "-" for those. See app.models.merchant.Merchant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4b1c2d3e4f5'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('merchants', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('merchants', 'created_at')
