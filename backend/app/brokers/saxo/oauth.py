"""OAuth2 Authorization Code + PKCE helpers for Saxo Bank."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """Return (verifier, challenge). S256 only."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def generate_state() -> str:
    return _b64url(secrets.token_bytes(24))


@dataclass(frozen=True)
class AuthorizeUrl:
    url: str
    state: str
    verifier: str


def build_authorize_url(
    *,
    authorize_endpoint: str,
    app_key: str,
    redirect_url: str,
) -> AuthorizeUrl:
    verifier, challenge = generate_pkce()
    state = generate_state()
    params = {
        "response_type": "code",
        "client_id": app_key,
        "redirect_uri": redirect_url,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return AuthorizeUrl(
        url=f"{authorize_endpoint}?{urlencode(params)}",
        state=state,
        verifier=verifier,
    )
