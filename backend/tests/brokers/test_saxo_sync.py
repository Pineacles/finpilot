"""Sync + live-prices tests for the Saxo adapter (order/trading path removed)."""
from __future__ import annotations

import time

import pytest
import respx

from app.services import settings as settings_svc

SIM = "https://gateway.saxobank.com/sim/openapi"
TOKEN_URL = "https://sim.logonvalidation.net/token"


@pytest.fixture
def saxo_adapter():
    from app.brokers.saxo.adapter import SaxoAdapter
    from app.brokers.saxo import instruments as saxo_instruments
    saxo_instruments._reset_cache_for_tests()
    return SaxoAdapter()


async def _seed_trading_ready(db, user_id) -> None:
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://example.test/cb",
        "saxo_access_token": "access-ok",
        "saxo_refresh_token": "refresh-ok",
        "saxo_token_expires_at": str(int(time.time()) + 1200),
    })


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
