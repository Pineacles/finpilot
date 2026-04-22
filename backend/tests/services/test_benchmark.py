"""Benchmark TWR: portfolio value reconstruction, equity filter, empty cases."""
from __future__ import annotations

import builtins
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest

from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction
from app.models.user import User
from app.services import benchmark as benchmark_svc
from app.services import classification as classification_svc


def _mk_days(start: int, end: int, step: int = -1):
    """Builtin range wrapper — we can't use `range` directly inside mock functions
    whose signatures shadow it with a string parameter."""
    return builtins.range(start, end, step)


async def _seed_user_and_account(db, user_id, name="Portfolio"):
    db.add(User(id=user_id, email=f"{user_id}@t.test", password_hash="x",
                api_key=f"apikey-{user_id}", display_name="t"))
    account = Account(user_id=user_id, name=name, type="brokerage", currency="USD")
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


def _mk_tx(user_id, account_id, symbol, ttype, qty, price, days_ago, currency="USD"):
    return StockTransaction(
        user_id=user_id, account_id=account_id,
        symbol=symbol, type=ttype, quantity=qty, price=price, fees=0,
        currency=currency,
        executed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


async def test_empty_state_returns_zero_series(db, user_id):
    await _seed_user_and_account(db, user_id)
    result = await benchmark_svc.compute_benchmark_comparison(db, user_id, range_key="1M")
    assert result.portfolio_series == []
    assert result.benchmark_series == []
    assert result.summary["portfolio_return_pct"] == 0.0
    assert "No stock transactions" in result.caveats[0]


async def test_etf_excluded_from_individual_series(db, user_id):
    """SPY classified as ETF must be in excluded_symbols, not counted_symbols."""
    acct = await _seed_user_and_account(db, user_id)
    db.add_all([
        _mk_tx(user_id, acct.id, "AAPL", "buy", 10, 150.0, days_ago=45),
        _mk_tx(user_id, acct.id, "SPY", "buy", 5, 400.0, days_ago=40),
    ])
    await db.commit()

    # Pre-classify so the service skips auto-detect (avoids Yahoo network)
    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")
    await classification_svc.set_classification(db, user_id, "SPY", "etf", source="user")

    # Mock price history so we don't hit Yahoo
    async def fake_history(ticker, range="1y", interval="1d"):  # noqa: A002
        # Flat $1 prices so TWR is zero — we only care about which symbols are counted
        today = datetime.now(timezone.utc).date()
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": 1.0}
            for d in _mk_days(60, -1, -1)
        ]

    async def fake_fx(f, t):
        return 1.0

    with patch("app.services.benchmark.get_history", side_effect=fake_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    counted = {s["symbol"] for s in result.counted_symbols}
    excluded = {s["symbol"] for s in result.excluded_symbols}
    assert "AAPL" in counted
    assert "SPY" not in counted
    assert "SPY" in excluded
    # The excluded SPY should be reason=classified_non_equity
    spy_excl = next(s for s in result.excluded_symbols if s["symbol"] == "SPY")
    assert spy_excl["reason"] == "classified_non_equity"
    assert spy_excl["asset_type"] == "etf"


async def test_twr_climbs_with_rising_prices(db, user_id):
    acct = await _seed_user_and_account(db, user_id)
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=45))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")

    # Rising prices: 100 → 110 over the period, no flows after initial buy
    today = datetime.now(timezone.utc).date()

    async def fake_history(ticker, range="1y", interval="1d"):  # noqa: A002
        if ticker == "AAPL":
            return [
                {"date": (today - timedelta(days=d)).isoformat(), "close": 100.0 + (45 - d) * 0.2}
                for d in _mk_days(45, -1, -1)
            ]
        if ticker == "SPY":
            # Benchmark flat — makes portfolio alpha obvious
            return [
                {"date": (today - timedelta(days=d)).isoformat(), "close": 400.0}
                for d in _mk_days(45, -1, -1)
            ]
        return []

    async def fake_fx(f, t):
        return 1.0

    with patch("app.services.benchmark.get_history", side_effect=fake_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    # Portfolio should be up (single equity climbed).
    assert result.summary["portfolio_return_pct"] > 0
    # Benchmark flat.
    assert abs(result.summary["benchmark_return_pct"]) < 0.01
    # Alpha matches portfolio.
    assert abs(result.summary["alpha_pct"] - result.summary["portfolio_return_pct"]) < 0.01
    # Series anchored at 100.
    assert result.portfolio_series[0]["index"] == 100.0
    assert result.benchmark_series[0]["index"] == 100.0


async def test_mid_period_buy_doesnt_create_fake_return(db, user_id):
    """TWR must ignore the cash inflow of a new buy — the return comes only from
    price movement of pre-existing holdings."""
    acct = await _seed_user_and_account(db, user_id)
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=45))
    # Second buy mid-period — should not show up as a return spike
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=15))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    async def fake_history(ticker, range="1y", interval="1d"):  # noqa: A002
        if ticker == "AAPL":
            return [
                {"date": (today - timedelta(days=d)).isoformat(), "close": 100.0}
                for d in _mk_days(60, -1, -1)
            ]
        if ticker == "SPY":
            return [
                {"date": (today - timedelta(days=d)).isoformat(), "close": 400.0}
                for d in _mk_days(60, -1, -1)
            ]
        return []

    async def fake_fx(f, t):
        return 1.0

    with patch("app.services.benchmark.get_history", side_effect=fake_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    # Flat prices + additional buy should give ~0% return, not a fake spike from the cash flow
    assert abs(result.summary["portfolio_return_pct"]) < 0.1


async def test_saxo_only_positions_flagged_as_caveat(db, user_id):
    """A position on a Saxo-named account with no StockTransaction row should be
    listed in excluded_symbols with reason 'saxo_only'."""
    db.add(User(id=user_id, email=f"{user_id}@t.test", password_hash="x",
                api_key=f"apikey-{user_id}", display_name="t"))
    manual_acct = Account(user_id=user_id, name="Portfolio", type="brokerage", currency="USD")
    saxo_acct = Account(user_id=user_id, name="Saxo sim [AK]", type="brokerage", currency="EUR")
    db.add_all([manual_acct, saxo_acct])
    await db.commit()
    await db.refresh(manual_acct)
    await db.refresh(saxo_acct)

    # Transaction-backed AAPL on manual account
    db.add(_mk_tx(user_id, manual_acct.id, "AAPL", "buy", 10, 100.0, days_ago=45))
    # Saxo-only position: no transaction, just a position row
    db.add(StockPosition(
        user_id=user_id, account_id=saxo_acct.id, symbol="MSFT", name="Microsoft",
        quantity=5, avg_cost_price=300.0, currency="USD",
    ))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")
    await classification_svc.set_classification(db, user_id, "MSFT", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    async def fake_history(ticker, range="1y", interval="1d"):  # noqa: A002
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": 100.0}
            for d in _mk_days(60, -1, -1)
        ]

    async def fake_fx(f, t):
        return 1.0

    with patch("app.services.benchmark.get_history", side_effect=fake_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M"
        )

    msft_excluded = [s for s in result.excluded_symbols if s["symbol"] == "MSFT" and s["reason"] == "saxo_only"]
    assert len(msft_excluded) == 1
    assert any("Saxo" in c for c in result.caveats)

    counted = {s["symbol"] for s in result.counted_symbols}
    assert "AAPL" in counted
    assert "MSFT" not in counted


async def test_custom_range_requires_start_and_end(db, user_id):
    await _seed_user_and_account(db, user_id)
    with pytest.raises(Exception):
        await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="CUSTOM", custom_start=None, custom_end=None
        )
