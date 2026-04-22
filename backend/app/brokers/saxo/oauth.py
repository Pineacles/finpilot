"""OAuth2 Authorization Code + PKCE helpers for Saxo Bank."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlencode


# ── Token refresh outcome classification ────────────────────────────────────
#
# Saxo's token endpoint returns 401 on invalid refresh tokens, 400 on malformed
# or expired requests, 5xx on transient outages. We split failures into two
# buckets so the retry loop doesn't hammer the endpoint when the refresh token
# is already dead, but does recover from transient errors.
#
# Permanent: re-auth is the only fix. Delete stored tokens, set needs_reauth.
# Transient: backoff and retry; keep tokens intact.


@dataclass
class RefreshResult:
    """Outcome of a single refresh attempt.

    `ok` is True when we got a fresh access_token. `permanent` distinguishes
    refresh-token-is-dead from a transient outage. `error` is a short human
    string for logging / surfacing to the user — MUST NOT contain the token.
    """
    tokens: dict[str, str] | None = None
    permanent: bool = False
    error: str = ""
    http_status: int | None = None

    @property
    def ok(self) -> bool:
        return self.tokens is not None and bool(self.tokens.get("access_token"))


# HTTP statuses that are terminal on the token endpoint — the refresh token
# itself is dead and retrying with it will never succeed.
_PERMANENT_TOKEN_STATUSES = {400, 401, 403}


# OAuth2 error codes that are always terminal regardless of HTTP status.
_PERMANENT_OAUTH_ERRORS = {
    "invalid_grant",       # refresh token expired / revoked / already used
    "invalid_client",      # app_key or app_secret wrong
    "unauthorized_client", # app not allowed to refresh
    "invalid_request",     # malformed payload — re-auth won't help, but still terminal here
}


def classify_refresh_error(
    *, http_status: int | None, oauth_error: str | None
) -> bool:
    """Return True if the error is permanent (don't retry — re-auth needed)."""
    if oauth_error and oauth_error.lower() in _PERMANENT_OAUTH_ERRORS:
        return True
    if http_status is None:
        return False  # network error → transient
    if http_status in _PERMANENT_TOKEN_STATUSES:
        return True
    if http_status >= 500:
        return False  # upstream outage → transient
    # Any other 4xx on the token endpoint: treat as permanent. Saxo's token
    # endpoint has no rate-limit response distinct from 429, and 429 IS
    # something to back off on, so we special-case it.
    if http_status == 429:
        return False
    return True


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
