import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_JWT_ISSUER = "finpilot"
_JWT_AUDIENCE = "finpilot"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def generate_api_key() -> str:
    return secrets.token_urlsafe(48)


API_KEY_HASH_PREFIX = "sha256:"


def hash_api_key(key: str) -> str:
    """Storage form of an agent API key. Keys are 288-bit random values, so a
    plain SHA-256 (no salt, no work factor) is enough and allows an indexed
    lookup."""
    return API_KEY_HASH_PREFIX + hashlib.sha256(key.encode()).hexdigest()


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        issuer=_JWT_ISSUER,
        audience=_JWT_AUDIENCE,
    )
