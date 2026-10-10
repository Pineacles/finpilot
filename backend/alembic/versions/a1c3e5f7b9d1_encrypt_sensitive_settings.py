"""encrypt gmail_app_password and saxo_access_token at rest

Revision ID: a1c3e5f7b9d1
Revises: f4b1c2d3e4f5
Create Date: 2026-10-10 14:00:00.000000

Encrypts existing plaintext rows with TOKEN_ENCRYPTION_KEY (Fernet). A no-op
when the key is not configured. Rows already carrying the enc:v1: prefix are
left alone. Downgrade decrypts them back to plaintext.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.crypto import decrypt_value, encrypt_value, encryption_enabled

revision: str = 'a1c3e5f7b9d1'
down_revision: Union[str, None] = 'f4b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEYS = ("gmail_app_password", "saxo_access_token")


def _rewrite(fn) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, value FROM user_settings WHERE key IN :keys AND value <> ''").bindparams(
            sa.bindparam("keys", expanding=True)
        ),
        {"keys": list(_KEYS)},
    ).fetchall()
    for row_id, value in rows:
        new = fn(value)
        if new != value:
            conn.execute(
                sa.text("UPDATE user_settings SET value = :v WHERE id = :id"),
                {"v": new, "id": row_id},
            )


def upgrade() -> None:
    if encryption_enabled():
        _rewrite(encrypt_value)


def downgrade() -> None:
    if encryption_enabled():
        _rewrite(decrypt_value)
