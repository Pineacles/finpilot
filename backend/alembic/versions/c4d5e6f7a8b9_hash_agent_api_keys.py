"""store agent API keys as SHA-256 hashes

Revision ID: c4d5e6f7a8b9
Revises: a1c3e5f7b9d1
Create Date: 2026-11-04 10:00:00.000000

Widens users.api_key and rewrites every plaintext key to ``sha256:<hex>`` in
place. Existing agents keep working: the header they send is hashed and
compared with the stored value. Rows already carrying the prefix are left
alone. Not reversible (a hash cannot be turned back into the key); after a
downgrade, regenerate keys in Settings.
"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'a1c3e5f7b9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PREFIX = "sha256:"


def upgrade() -> None:
    op.alter_column("users", "api_key", existing_type=sa.String(64), type_=sa.String(128), existing_nullable=False)
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, api_key FROM users")).fetchall()
    for row_id, key in rows:
        if key and not key.startswith(_PREFIX):
            conn.execute(
                sa.text("UPDATE users SET api_key = :v WHERE id = :id"),
                {"v": _PREFIX + hashlib.sha256(key.encode()).hexdigest(), "id": row_id},
            )


def downgrade() -> None:
    # Hashes cannot be reversed and do not fit the old column width; keep the
    # column as is. Keys must be regenerated after a downgrade.
    pass
