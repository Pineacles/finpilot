"""Trading path tests: instrument lookup, precheck, place, cancel, modify, sync."""
from __future__ import annotations

import time

import httpx
import pytest
import respx

from app.brokers.base import TradingDisabledError
from app.brokers.saxo import instruments as saxo_instruments
from app.services import settings as settings_svc

SIM = "https://gateway.saxobank.com/sim/openapi"
TOKEN_URL = "https://sim.logonvalidation.net/token"


@pytest.fixture
def saxo_adapter():
    from app.brokers.saxo.adapter import SaxoAdapter
    saxo_instruments._reset_cache_for_tests()
    return SaxoAdapter()


async def _seed_trading_ready(db, user_id) -> None:
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_trading_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://example.test/cb",
        "saxo_access_token": "access-ok",
        "saxo_refresh_token": "refresh-ok",
        "saxo_token_expires_at": str(int(time.time()) + 1200),
    })


async def test_trading_gate_rejects_when_trading_flag_off(db, user_id, saxo_adapter):
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://example.test/cb",
        "saxo_access_token": "access-ok",
        "saxo_refresh_token": "refresh-ok",
        "saxo_token_expires_at": str(int(time.time()) + 1200),
        # saxo_trading_enabled intentionally absent — defaults to "off"
    })
    with pytest.raises(TradingDisabledError):
        await saxo_adapter.precheck_order(
            db, user_id, account_key="AK", symbol="AAPL",
            buy_sell="Buy", amount=1, order_type="Market",
        )


async def test_precheck_and_place_market_order(db, user_id, saxo_adapter):
    await _seed_trading_ready(db, user_id)
    # assert_all_called=False because this test calls the adapter directly, not
    # the REST endpoint — so the post-trade sync routes are legitimately unused.
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{SIM}/ref/v1/instruments").respond(json={
            "Data": [{"Identifier": 211, "Symbol": "AAPL", "Description": "Apple Inc.",
                      "AssetType": "Stock", "CurrencyCode": "USD"}]
        })
        precheck_route = mock.post(f"{SIM}/trade/v2/orders/precheck").respond(json={
            "PreCheckResult": "Ok",
            "EstimatedCashRequired": 267.70,
            "EstimatedCommissions": 0.50,
            "Currency": "USD",
        })
        place_route = mock.post(f"{SIM}/trade/v2/orders").respond(
            status_code=201,
            json={"OrderId": "5037889999"},
        )

        precheck = await saxo_adapter.precheck_order(
            db, user_id, account_key="AK", symbol="AAPL",
            buy_sell="Buy", amount=1, order_type="Market",
        )
        assert precheck.ok
        assert precheck.estimated_cash_required == pytest.approx(267.70)
        assert precheck.estimated_fees == pytest.approx(0.50)
        assert precheck_route.called

        ack = await saxo_adapter.place_order(
            db, user_id, account_key="AK", symbol="AAPL",
            buy_sell="Buy", amount=1, order_type="Market",
        )
        assert ack.order_id == "5037889999"
        assert place_route.called


async def test_modify_fetches_existing_then_patches_full_payload(db, user_id, saxo_adapter):
    await _seed_trading_ready(db, user_id)
    with respx.mock() as mock:
        mock.get(f"{SIM}/port/v1/accounts/me").respond(json={
            "Data": [{"AccountKey": "AK", "ClientKey": "CK", "DisplayName": "SIM", "Currency": "EUR"}]
        })
        mock.get(f"{SIM}/port/v1/orders/me").respond(json={
            "Data": [{
                "OrderId": "42", "Uic": 211, "AssetType": "Stock",
                "BuySell": "Buy", "Amount": 1, "OpenOrderType": "Limit",
                "Price": 240.0, "Duration": {"DurationType": "GoodTillCancel"},
            }]
        })

        captured = {}
        def _patch_side_effect(request):
            import json as _json
            captured["payload"] = _json.loads(request.content.decode())
            return httpx.Response(200, json={"OrderId": "42"})
        mock.patch(f"{SIM}/trade/v2/orders").mock(side_effect=_patch_side_effect)

        await saxo_adapter.modify_order(
            db, user_id, order_id="42", account_key="AK", limit_price=245,
        )

    payload = captured["payload"]
    assert payload["OrderId"] == "42"
    assert payload["Uic"] == 211
    assert payload["AssetType"] == "Stock"
    assert payload["BuySell"] == "Buy"
    assert payload["Amount"] == 1
    assert payload["OrderType"] == "Limit"
    assert payload["OrderPrice"] == 245
    assert payload["OrderDuration"] == {"DurationType": "GoodTillCancel"}


async def test_cancel_order_hits_delete_with_account_key(db, user_id, saxo_adapter):
    await _seed_trading_ready(db, user_id)
    with respx.mock() as mock:
        route = mock.delete(f"{SIM}/trade/v2/orders/42").respond(json={"OrderId": "42"})
        await saxo_adapter.cancel_order(db, user_id, order_id="42", account_key="AK")
    assert route.called


async def test_sync_upserts_positions_and_updates_cash(db, user_id, saxo_adapter):
    from app.brokers.saxo import sync as saxo_sync
    from app.brokers.base import BrokerAccount, BrokerBalance, BrokerPosition
    from app.models.account import Account
    from app.models.stock import StockPosition
    from sqlalchemy import select, and_

    # Insert a fake user row so FK constraints pass on Postgres; SQLite is lax.
    from app.models.user import User
    db.add(User(id=user_id, email=f"{user_id}@t.test", password_hash="x",
                api_key=f"apikey-{user_id}", display_name="t"))
    await db.commit()

    broker_account = BrokerAccount(external_id="AK", display_name="SIM", currency="EUR", environment="sim")
    local_account = await saxo_sync.get_or_create_saxo_account(
        db, user_id=user_id, environment="sim", broker_account=broker_account
    )
    balance = BrokerBalance(account_external_id="AK", cash=998_000.0, currency="EUR")
    positions = [
        BrokerPosition(
            account_external_id="AK", symbol="AAPL", name="Apple Inc.",
            quantity=5, avg_price=267.70, currency="USD",
            market_price=270.0, market_value=1350.0, unrealized_pnl=11.50,
        )
    ]

    result = await saxo_sync.sync_positions(
        db, user_id=user_id, account=local_account,
        broker_positions=positions, broker_balance=balance,
    )

    assert result.positions_upserted == 1
    assert result.positions_removed == 0

    row_result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user_id,
            StockPosition.account_id == local_account.id,
        ))
    )
    rows = row_result.scalars().all()
    assert len(rows) == 1
    assert rows[0].symbol == "AAPL"
    assert rows[0].quantity == 5
    assert rows[0].avg_cost_price == pytest.approx(267.70)

    # And cash landed on the Account row.
    acct = (await db.execute(select(Account).where(Account.id == local_account.id))).scalar_one()
    assert acct.balance == pytest.approx(998_000.0)

    # Second sync with empty positions removes the stale one.
    result2 = await saxo_sync.sync_positions(
        db, user_id=user_id, account=local_account,
        broker_positions=[], broker_balance=balance,
    )
    assert result2.positions_removed == 1


async def test_live_prices_hits_infoprices(db, user_id, saxo_adapter):
    await _seed_trading_ready(db, user_id)
    with respx.mock() as mock:
        mock.get(f"{SIM}/ref/v1/instruments").respond(json={
            "Data": [{"Identifier": 211, "Symbol": "AAPL", "AssetType": "Stock", "CurrencyCode": "USD"}]
        })
        mock.get(f"{SIM}/trade/v1/infoprices/list").respond(json={
            "Data": [{
                "Uic": 211,
                "Quote": {"Mid": 267.75},
                "PriceInfo": {"NetChange": 1.25, "PercentChange": 0.47},
            }]
        })
        quotes = await saxo_adapter.get_live_prices(db, user_id, symbols=["AAPL"])
    assert "AAPL" in quotes
    assert quotes["AAPL"]["price"] == pytest.approx(267.75)
    assert quotes["AAPL"]["change_pct"] == pytest.approx(0.47)
    assert quotes["AAPL"]["source"] == "saxo"
