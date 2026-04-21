"""Happy-path adapter tests: accounts, balances, positions, health, refresh."""
from __future__ import annotations

import time

import pytest
import respx

from app.brokers.base import AuthState
from app.services import settings as settings_svc

SIM = "https://gateway.saxobank.com/sim/openapi"
TOKEN = "https://sim.logonvalidation.net/token"


@pytest.fixture
def saxo_adapter():
    from app.brokers.saxo.adapter import SaxoAdapter
    return SaxoAdapter()


async def _seed_connected(db, user_id, *, expires_in_seconds: int = 1200) -> None:
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://finpilot.example.com/settings/saxo/callback",
        "saxo_access_token": "access-v1",
        "saxo_refresh_token": "refresh-v1",
        "saxo_token_expires_at": str(int(time.time()) + expires_in_seconds),
    })


async def test_health_check_hits_diagnostics(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id)
    with respx.mock() as mock:
        route = mock.get(f"{SIM}/root/v1/diagnostics/get").respond(status_code=200, content=b"")
        ok = await saxo_adapter.health_check(db, user_id)
    assert ok is True
    assert route.called


async def test_get_accounts_maps_payload(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id)
    with respx.mock() as mock:
        mock.get(f"{SIM}/port/v1/accounts/me").respond(json={
            "Data": [
                {"AccountKey": "AK-1", "ClientKey": "CK-1", "DisplayName": "Test User SIM", "Currency": "CHF"},
                {"AccountKey": "AK-2", "ClientKey": "CK-1", "DisplayName": "Sub", "Currency": "USD"},
            ]
        })
        accounts = await saxo_adapter.get_accounts(db, user_id)

    assert [a.external_id for a in accounts] == ["AK-1", "AK-2"]
    assert accounts[0].display_name == "Test User SIM"
    assert accounts[0].currency == "CHF"
    assert all(a.environment == "sim" for a in accounts)


async def test_get_balances_maps_payload(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id)
    with respx.mock() as mock:
        mock.get(f"{SIM}/port/v1/accounts/me").respond(json={
            "Data": [{"AccountKey": "AK-1", "ClientKey": "CK-1", "DisplayName": "SIM", "Currency": "CHF"}]
        })
        mock.get(f"{SIM}/port/v1/balances").respond(json={
            "Currency": "CHF",
            "CashBalance": 12345.67,
            "TotalValue": 50000.0,
            "UnrealizedMarginProfitLoss": 42.5,
        })
        balance = await saxo_adapter.get_balances(db, user_id, "AK-1")

    assert balance.account_external_id == "AK-1"
    assert balance.cash == pytest.approx(12345.67)
    assert balance.currency == "CHF"
    assert balance.total_value == pytest.approx(50000.0)
    assert balance.unrealized_pnl == pytest.approx(42.5)


async def test_get_positions_maps_payload(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id)
    with respx.mock() as mock:
        mock.get(f"{SIM}/port/v1/accounts/me").respond(json={
            "Data": [{"AccountKey": "AK-1", "ClientKey": "CK-1", "DisplayName": "SIM", "Currency": "CHF"}]
        })
        mock.get(f"{SIM}/port/v1/positions").respond(json={
            "Data": [{
                "DisplayAndFormat": {"Symbol": "AAPL", "Description": "Apple Inc.", "Currency": "USD"},
                "PositionBase": {"Amount": 10, "OpenPrice": 150.0, "AccountingCurrency": "USD"},
                "PositionView": {"CurrentPrice": 180.0, "MarketValue": 1800.0, "ProfitLossOnTrade": 300.0},
            }]
        })
        positions = await saxo_adapter.get_positions(db, user_id, "AK-1")

    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "AAPL"
    assert p.quantity == 10
    assert p.avg_price == 150.0
    assert p.market_price == 180.0
    assert p.unrealized_pnl == 300.0
    assert p.currency == "USD"


async def test_expired_access_token_triggers_refresh(db, user_id, saxo_adapter):
    # Access token already expired — any call should refresh first.
    await _seed_connected(db, user_id, expires_in_seconds=-60)

    with respx.mock() as mock:
        token_route = mock.post(TOKEN).respond(json={
            "access_token": "access-v2",
            "refresh_token": "refresh-v2",
            "expires_in": 1200,
        })
        mock.get(f"{SIM}/root/v1/diagnostics/get").respond(status_code=200, content=b"")
        ok = await saxo_adapter.health_check(db, user_id)

    assert ok is True
    assert token_route.called

    # After refresh, persistence reflects the rotated refresh token.
    stored_access = await settings_svc.get_setting(db, user_id, "saxo_access_token")
    stored_refresh = await settings_svc.get_setting(db, user_id, "saxo_refresh_token")
    assert stored_access == "access-v2"
    assert stored_refresh == "refresh-v2"


async def test_refresh_failure_clears_tokens_and_flags_reauth(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id, expires_in_seconds=-60)
    with respx.mock() as mock:
        mock.post(TOKEN).respond(status_code=400, json={"error": "invalid_grant"})
        with pytest.raises(RuntimeError, match="needs_auth"):
            await saxo_adapter.get_accounts(db, user_id)

    # Tokens are wiped so the UI can display NEEDS_AUTH.
    access = await settings_svc.get_setting(db, user_id, "saxo_access_token")
    refresh = await settings_svc.get_setting(db, user_id, "saxo_refresh_token")
    assert access == ""
    assert refresh == ""

    status = await saxo_adapter.status(db, user_id)
    assert status.state == AuthState.NEEDS_AUTH


async def test_retry_on_5xx_then_success(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id)
    with respx.mock() as mock:
        call = [0]
        def _responder(request):
            import httpx
            call[0] += 1
            if call[0] == 1:
                return httpx.Response(503, json={"ErrorCode": "Busy"})
            return httpx.Response(200, json={"Data": []})
        mock.get(f"{SIM}/port/v1/accounts/me").mock(side_effect=_responder)
        accounts = await saxo_adapter.get_accounts(db, user_id)

    assert accounts == []
    assert call[0] == 2  # one retry


async def test_no_retry_on_4xx(db, user_id, saxo_adapter):
    await _seed_connected(db, user_id)
    with respx.mock() as mock:
        route = mock.get(f"{SIM}/port/v1/accounts/me").respond(status_code=401, json={"ErrorCode": "Unauthorized"})
        with pytest.raises(Exception):
            await saxo_adapter.get_accounts(db, user_id)
    assert route.call_count == 1
