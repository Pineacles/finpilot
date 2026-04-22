"""Refresh-token handling: permanent vs transient classification, retry,
and the proactive scheduler's user-selection query."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.brokers.saxo import instruments as saxo_instruments
from app.brokers.saxo.oauth import classify_refresh_error
from app.services import settings as settings_svc


SIM = "https://gateway.saxobank.com/sim/openapi"
TOKEN_URL = "https://sim.logonvalidation.net/token"


@pytest.fixture
def saxo_adapter():
    from app.brokers.saxo.adapter import SaxoAdapter
    saxo_instruments._reset_cache_for_tests()
    return SaxoAdapter()


async def _seed_expired_tokens(db, user_id) -> None:
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://example.test/cb",
        "saxo_access_token": "old-expired",
        "saxo_refresh_token": "refresh-old",
        "saxo_token_expires_at": str(int(time.time()) - 60),  # already expired
    })


# ── Classification ──────────────────────────────────────────────────────────


def test_classify_invalid_grant_is_permanent():
    assert classify_refresh_error(http_status=400, oauth_error="invalid_grant") is True


def test_classify_invalid_client_is_permanent():
    assert classify_refresh_error(http_status=401, oauth_error="invalid_client") is True


def test_classify_401_without_error_code_is_permanent():
    # 401 on the token endpoint means the refresh token or client creds are bad — re-auth needed.
    assert classify_refresh_error(http_status=401, oauth_error=None) is True


def test_classify_5xx_is_transient():
    assert classify_refresh_error(http_status=500, oauth_error=None) is False
    assert classify_refresh_error(http_status=503, oauth_error=None) is False


def test_classify_429_is_transient():
    assert classify_refresh_error(http_status=429, oauth_error=None) is False


def test_classify_network_error_is_transient():
    assert classify_refresh_error(http_status=None, oauth_error=None) is False


# ── Permanent refresh failure → needs_reauth ────────────────────────────────


async def test_permanent_refresh_failure_sets_needs_reauth(db, user_id, saxo_adapter):
    await _seed_expired_tokens(db, user_id)

    with respx.mock() as mock:
        mock.post(TOKEN_URL).respond(
            status_code=401,
            json={"error": "invalid_grant", "error_description": "refresh token expired"},
        )
        with pytest.raises(RuntimeError, match="needs_auth"):
            await saxo_adapter._token_and_env(db, user_id)

    # Tokens wiped; needs_reauth flag set
    assert await settings_svc.get_setting(db, user_id, "saxo_access_token") == ""
    assert await settings_svc.get_setting(db, user_id, "saxo_refresh_token") == ""
    assert await settings_svc.get_setting(db, user_id, "saxo_needs_reauth") == "1"
    last_error = await settings_svc.get_setting(db, user_id, "saxo_last_error")
    assert "refresh_failed" in last_error


async def test_status_reports_needs_auth_when_flag_set(db, user_id, saxo_adapter):
    # Set up a user with tokens still present but needs_reauth flagged
    await _seed_expired_tokens(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {"saxo_needs_reauth": "1"})
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_access_token": "some-access",  # stale but present
    })

    from app.brokers.base import AuthState
    status = await saxo_adapter.status(db, user_id)
    assert status.state == AuthState.NEEDS_AUTH


# ── Transient refresh failure → retry then succeed ──────────────────────────


async def test_transient_failure_retries_then_succeeds(db, user_id, saxo_adapter):
    await _seed_expired_tokens(db, user_id)

    calls = {"n": 0}

    def _token_side_effect(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "service_unavailable"})
        return httpx.Response(
            200,
            json={
                "access_token": "fresh-access",
                "refresh_token": "fresh-refresh",
                "expires_in": 1200,
                "token_type": "Bearer",
            },
        )

    with patch("app.brokers.saxo.adapter.asyncio.sleep", new=AsyncMock()):  # skip backoff
        with respx.mock() as mock:
            mock.post(TOKEN_URL).mock(side_effect=_token_side_effect)
            token, _ = await saxo_adapter._token_and_env(db, user_id)

    assert token == "fresh-access"
    assert calls["n"] == 3
    assert await settings_svc.get_setting(db, user_id, "saxo_access_token") == "fresh-access"
    assert await settings_svc.get_setting(db, user_id, "saxo_refresh_token") == "fresh-refresh"
    # A successful refresh clears needs_reauth
    assert await settings_svc.get_setting(db, user_id, "saxo_needs_reauth") == "0"


async def test_transient_exhausted_keeps_tokens(db, user_id, saxo_adapter):
    """All 3 attempts fail with 503 — do NOT wipe tokens (it's Saxo's problem)."""
    await _seed_expired_tokens(db, user_id)

    with patch("app.brokers.saxo.adapter.asyncio.sleep", new=AsyncMock()):
        with respx.mock() as mock:
            mock.post(TOKEN_URL).respond(status_code=503, json={"error": "service_unavailable"})
            with pytest.raises(RuntimeError, match="needs_auth"):
                await saxo_adapter._token_and_env(db, user_id)

    # Tokens still present (user hasn't lost re-auth yet — Saxo was just flaky)
    assert await settings_svc.get_setting(db, user_id, "saxo_refresh_token") == "refresh-old"
    assert await settings_svc.get_setting(db, user_id, "saxo_needs_reauth") in ("", "0")
    last_error = await settings_svc.get_setting(db, user_id, "saxo_last_error")
    assert "refresh_transient_exhausted" in last_error


# ── Scheduler user-selection ────────────────────────────────────────────────


async def test_scheduler_picks_users_near_expiry(db, user_id):
    """The proactive refresh scheduler should return users with tokens
    within the refresh buffer; not users that are fresh or already need reauth."""
    from app.services.saxo_scheduler import _users_to_refresh, _PROACTIVE_REFRESH_BUFFER
    from app.core.database import async_session as real_async_session

    # Seed: this user needs refresh (expiry in 60s, well within buffer)
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_refresh_token": "rt",
        "saxo_token_expires_at": str(int(time.time()) + 60),
        "saxo_needs_reauth": "0",
    })

    # Swap async_session to use our in-memory sqlite engine
    async def _fake_session_ctx():
        class _Ctx:
            async def __aenter__(self_inner): return db
            async def __aexit__(self_inner, *a): return False
        return _Ctx()

    # The scheduler calls async_session() directly; monkey-patch at module scope
    import app.services.saxo_scheduler as sched
    original = sched.async_session
    sched.async_session = lambda: _FakeSession(db)
    try:
        users = await _users_to_refresh()
    finally:
        sched.async_session = original

    assert user_id in users


class _FakeSession:
    def __init__(self, db): self._db = db
    async def __aenter__(self): return self._db
    async def __aexit__(self, *a): return False


async def test_scheduler_skips_fresh_tokens(db, user_id):
    """Users whose tokens are far from expiry should not be picked up."""
    from app.services.saxo_scheduler import _users_to_refresh
    import app.services.saxo_scheduler as sched

    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_refresh_token": "rt",
        "saxo_token_expires_at": str(int(time.time()) + 3600),  # 1 hour from now
        "saxo_needs_reauth": "0",
    })

    original = sched.async_session
    sched.async_session = lambda: _FakeSession(db)
    try:
        users = await _users_to_refresh()
    finally:
        sched.async_session = original

    assert user_id not in users


async def test_scheduler_skips_needs_reauth_users(db, user_id):
    """Once a user is flagged needs_reauth the scheduler stops trying —
    only the UI Reconnect can fix it."""
    from app.services.saxo_scheduler import _users_to_refresh
    import app.services.saxo_scheduler as sched

    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_refresh_token": "rt",  # still there, but flag is set
        "saxo_token_expires_at": str(int(time.time()) + 60),
        "saxo_needs_reauth": "1",
    })

    original = sched.async_session
    sched.async_session = lambda: _FakeSession(db)
    try:
        users = await _users_to_refresh()
    finally:
        sched.async_session = original

    assert user_id not in users
