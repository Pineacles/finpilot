"""add settlement_patterns to accounts

Revision ID: d1e2f3a4b5c6
Revises: f3a8c91b5d2e
Create Date: 2026-07-08 00:10:00.000000

Adds a nullable JSON column so each credit_card account can configure its
own issuer-match keywords for services/settlement.py (Cumulus/Cembra
settlement auto-reset). Empty/None falls back to the built-in default
patterns (Cembra/Migros Cumulus + Viseca) at read time — no backfill needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'f3a8c91b5d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('settlement_patterns', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('accounts', 'settlement_patterns')
