"""Encryption at rest for a few sensitive user settings (Fernet).

Values are stored as ``enc:v1:<fernet token>``. Reads accept legacy plaintext
(no prefix) so existing rows keep working until the migration encrypts them.
With no TOKEN_ENCRYPTION_KEY configured, encryption is disabled and values are
stored as before. Losing the key makes encrypted values unreadable: they read
back as empty and must be re-entered.
"""
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"


@lru_cache(maxsize=4)
def _fernet_for(keys: str) -> MultiFernet | None:
    parts = [k.strip() for k in keys.split(",") if k.strip()]
    if not parts:
        return None
    return MultiFernet([Fernet(k.encode()) for k in parts])


def _fernet() -> MultiFernet | None:
    return _fernet_for(settings.TOKEN_ENCRYPTION_KEY)


def encryption_enabled() -> bool:
    return _fernet() is not None


def encrypt_value(value: str) -> str:
    f = _fernet()
    if not value or f is None or value.startswith(PREFIX):
        return value
    return PREFIX + f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value
    f = _fernet()
    if f is None:
        logger.error("Encrypted setting found but TOKEN_ENCRYPTION_KEY is not set")
        return ""
    try:
        return f.decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        logger.error("Could not decrypt a stored setting (wrong TOKEN_ENCRYPTION_KEY?)")
        return ""
