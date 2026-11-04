"""encrypt Saxo secrets, AI keys and auth headers at rest

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-04 10:05:00.000000

Extends a1c3e5f7b9d1 to saxo_app_secret, saxo_refresh_token, ai_api_key,
anthropic_api_key and the *_auth_header settings. A no-op when
TOKEN_ENCRYPTION_KEY is not configured. Reads already accept legacy plaintext,
so rows written before this migration keep working either way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.crypto import decrypt_value, encrypt_value, encryption_enabled

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEYS = (
    "saxo_app_secret",
    "saxo_refresh_token",
    "ai_api_key",
    "anthropic_api_key",
    "ai_auth_header",
    "analysis_auth_header",
    "agent_auth_header",
)


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
