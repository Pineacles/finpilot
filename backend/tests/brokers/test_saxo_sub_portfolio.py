"""Tests for GET /api/brokers/saxo/sub-portfolio connection-gating.

The endpoint must return connected=False whenever:
  - saxo_enabled != "1"
  - saxo_enabled="1" but neither access nor refresh token exists
  - saxo_needs_reauth="1" (tokens present but known-dead)

And connected=True only when enabled + has tokens + not in reauth state.

We call the service function indirectly by invoking the endpoint handler
with a fake DB + user, replicating the pattern used in test_saxo_adapter.py.
"""
from __future__ import annotations

import pytest

from app.models.account import Account
from app.models.user import User
from app.services import settings as settings_svc


async def _seed_user(db, user_id):
    db.add(User(
        id=user_id, email=f"{user_id}@t.test",
        password_hash="x", api_key=f"apikey-{user_id}", display_name="t",
    ))
    await db.commit()


async def _seed_saxo_account(db, user_id):
    """Add a local Account row with the Saxo prefix (stale data after disconnect)."""
    acct = Account(
        user_id=user_id,
        name="Saxo sim [AK-TEST]",
        type="brokerage",
        currency="CHF",
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)
    return acct


async def _call_endpoint(db, user_id):
    """Call the endpoint handler directly without HTTP overhead."""
    from app.api.endpoints.brokers import saxo_sub_portfolio
    from app.models.user import User as UserModel

    class FakeUser:
        id = user_id

    return await saxo_sub_portfolio(user=FakeUser(), db=db)


# ---------------------------------------------------------------------------
# 1. Account rows exist, but saxo_enabled=0 → connected=False
# ---------------------------------------------------------------------------

async def test_disabled_flag_returns_not_connected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_account(db, user_id)

    # saxo_enabled explicitly off
    await settings_svc.set_setting(db, user_id, "saxo_enabled", "0")
    await settings_svc.set_setting(db, user_id, "saxo_access_token", "tok")
    await settings_svc.set_setting(db, user_id, "saxo_refresh_token", "rtok")

    result = await _call_endpoint(db, user_id)
    assert result["connected"] is False
    assert result["accounts"] == []


# ---------------------------------------------------------------------------
# 2. saxo_enabled=1 but no tokens → connected=False
# ---------------------------------------------------------------------------

async def test_enabled_but_no_tokens_returns_not_connected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_account(db, user_id)

    await settings_svc.set_setting(db, user_id, "saxo_enabled", "1")
    # Do not set access or refresh tokens — they remain empty strings / default

    result = await _call_endpoint(db, user_id)
    assert result["connected"] is False
    assert result["accounts"] == []


# ---------------------------------------------------------------------------
# 3. saxo_needs_reauth=1 (tokens may exist but are known-dead) → connected=False
# ---------------------------------------------------------------------------

async def test_needs_reauth_returns_not_connected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_account(db, user_id)

    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_access_token": "stale-access",
        "saxo_refresh_token": "stale-refresh",
        "saxo_needs_reauth": "1",
    })

    result = await _call_endpoint(db, user_id)
    assert result["connected"] is False
    assert result["accounts"] == []


# ---------------------------------------------------------------------------
# 4. Fully connected → connected=True with account data
# ---------------------------------------------------------------------------

async def test_fully_connected_returns_connected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_account(db, user_id)

    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_access_token": "valid-access",
        "saxo_refresh_token": "valid-refresh",
        "saxo_needs_reauth": "0",
    })

    result = await _call_endpoint(db, user_id)
    assert result["connected"] is True
    assert len(result["accounts"]) == 1
    assert "Saxo" in result["accounts"][0]["name"]
