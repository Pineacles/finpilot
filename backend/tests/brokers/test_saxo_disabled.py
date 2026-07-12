"""Disabled-state kill-switch: flag off ⇒ zero outbound HTTP calls."""
from __future__ import annotations

import pytest
import respx

from app.brokers import get_adapter
from app.brokers.base import AuthState
from app.services import settings as settings_svc


@pytest.fixture
def saxo_adapter():
    # Fresh instance so the per-test token-bucket counters are pristine.
    from app.brokers.saxo.adapter import SaxoAdapter
    return SaxoAdapter()


async def test_every_method_short_circuits_when_disabled(db, user_id, saxo_adapter):
    # saxo_enabled is unset → treated as disabled. Pre-populate fake tokens so
    # that if the adapter forgot its flag check it would try to hit the network.
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://your-finpilot-domain.example.com/settings/saxo/callback",
        "saxo_access_token": "a-real-looking-token",
        "saxo_refresh_token": "a-real-looking-refresh",
        "saxo_token_expires_at": "9999999999",
    })

    with respx.mock(assert_all_called=False) as mock:
        # Intentionally do NOT register any routes. A real HTTP attempt will raise.
        status = await saxo_adapter.status(db, user_id)
        assert status.state == AuthState.DISABLED

        auth = await saxo_adapter.authenticate(db, user_id)
        assert auth.state == AuthState.DISABLED

        health = await saxo_adapter.health_check(db, user_id)
        assert health is False

        accounts = await saxo_adapter.get_accounts(db, user_id)
        assert accounts == []

        positions = await saxo_adapter.get_positions(db, user_id, "AK")
        assert positions == []

        balance = await saxo_adapter.get_balances(db, user_id, "AK")
        assert balance.cash == 0.0

        # respx sees no calls at all
        assert mock.calls.call_count == 0


async def test_flip_off_at_runtime_halts_activity(db, user_id, saxo_adapter):
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://your-finpilot-domain.example.com/settings/saxo/callback",
        "saxo_access_token": "valid-token",
        "saxo_refresh_token": "valid-refresh",
        "saxo_token_expires_at": "9999999999",
    })

    SIM = "https://gateway.saxobank.com/sim/openapi"
    # Phase 1: enabled, one real call that respx satisfies.
    with respx.mock() as mock:
        route_on = mock.get(f"{SIM}/port/v1/accounts/me").respond(
            json={"Data": [{"AccountKey": "AK1", "ClientKey": "CK1", "DisplayName": "SIM", "Currency": "USD"}]}
        )
        accounts = await saxo_adapter.get_accounts(db, user_id)
        assert len(accounts) == 1
        assert route_on.called

    # Flip off at runtime: next call must make zero HTTP traffic.
    await settings_svc.set_many_atomic(db, user_id, {"saxo_enabled": "0"})
    with respx.mock(assert_all_called=False) as mock:
        route_off = mock.get(f"{SIM}/port/v1/accounts/me").respond(json={"Data": []})
        accounts2 = await saxo_adapter.get_accounts(db, user_id)
        assert accounts2 == []
        assert route_off.call_count == 0
        assert mock.calls.call_count == 0
