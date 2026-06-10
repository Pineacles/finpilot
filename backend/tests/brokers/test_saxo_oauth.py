"""OAuth PKCE flow: authorize URL shape, state validation, token persistence."""
from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
import respx

from app.brokers.base import AuthState
from app.brokers.saxo.oauth import build_authorize_url, generate_pkce
from app.services import settings as settings_svc

TOKEN_URL = "https://sim.logonvalidation.net/token"


@pytest.fixture
def saxo_adapter():
    from app.brokers.saxo.adapter import SaxoAdapter
    return SaxoAdapter()


async def _seed_configured(db, user_id):
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "app-key-xyz",
        "saxo_app_secret": "app-secret-xyz",
        "saxo_redirect_url": "https://your-finpilot-domain.example.com/settings/saxo/callback",
    })


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = generate_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_authorize_url_shape():
    built = build_authorize_url(
        authorize_endpoint="https://sim.logonvalidation.net/authorize",
        app_key="app-k",
        redirect_url="https://example.test/cb",
    )
    parsed = urlparse(built.url)
    qs = parse_qs(parsed.query)
    assert qs["response_type"] == ["code"]
    assert qs["client_id"] == ["app-k"]
    assert qs["redirect_uri"] == ["https://example.test/cb"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["state"] == [built.state]
    assert len(built.verifier) >= 43  # RFC 7636 minimum


async def test_authenticate_persists_verifier_and_state(db, user_id, saxo_adapter):
    await _seed_configured(db, user_id)
    status = await saxo_adapter.authenticate(db, user_id)

    assert status.state == AuthState.CONNECTING
    assert status.detail and status.detail.startswith("https://sim.logonvalidation.net/authorize?")
    verifier = await settings_svc.get_setting(db, user_id, "saxo_pkce_verifier")
    state = await settings_svc.get_setting(db, user_id, "saxo_oauth_state")
    assert verifier
    assert state
    parsed_state = parse_qs(urlparse(status.detail).query)["state"][0]
    assert parsed_state == state


async def test_complete_oauth_rejects_mismatched_state(db, user_id, saxo_adapter):
    await _seed_configured(db, user_id)
    await saxo_adapter.authenticate(db, user_id)

    result = await saxo_adapter.complete_oauth(db, user_id, code="c", state="not-the-right-state")
    assert result.state == AuthState.ERROR
    assert result.last_error == "invalid_state"
    # Tokens never written
    assert await settings_svc.get_setting(db, user_id, "saxo_access_token") == ""


async def test_complete_oauth_exchanges_code_and_persists_tokens(db, user_id, saxo_adapter):
    await _seed_configured(db, user_id)
    init = await saxo_adapter.authenticate(db, user_id)
    real_state = parse_qs(urlparse(init.detail).query)["state"][0]

    with respx.mock() as mock:
        token_route = mock.post(TOKEN_URL).respond(json={
            "access_token": "acc-1",
            "refresh_token": "ref-1",
            "expires_in": 1200,
        })
        result = await saxo_adapter.complete_oauth(db, user_id, code="auth-code", state=real_state)

    assert result.state == AuthState.CONNECTED
    assert token_route.called

    # Tokens atomically persisted; PKCE verifier wiped.
    assert await settings_svc.get_setting(db, user_id, "saxo_access_token") == "acc-1"
    assert await settings_svc.get_setting(db, user_id, "saxo_refresh_token") == "ref-1"
    assert await settings_svc.get_setting(db, user_id, "saxo_pkce_verifier") == ""
    assert await settings_svc.get_setting(db, user_id, "saxo_oauth_state") == ""


async def test_token_exchange_failure_surfaces_as_error_state(db, user_id, saxo_adapter):
    await _seed_configured(db, user_id)
    init = await saxo_adapter.authenticate(db, user_id)
    real_state = parse_qs(urlparse(init.detail).query)["state"][0]

    with respx.mock() as mock:
        mock.post(TOKEN_URL).respond(status_code=400, json={"error": "invalid_code"})
        result = await saxo_adapter.complete_oauth(db, user_id, code="bad", state=real_state)

    assert result.state == AuthState.ERROR
    assert result.last_error == "token_exchange_failed"
    assert await settings_svc.get_setting(db, user_id, "saxo_access_token") == ""
