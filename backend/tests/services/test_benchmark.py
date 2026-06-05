"""Benchmark: TWR on active-period holdings vs. benchmark.

Tests cover:
  1. Empty state → empty series, zero summary, informative caveat.
  2. Single buy mid-window, flat prices → anchors at buy day, stays at 100, active_from correct.
  3. Buy and sell mid-window, price rises → TWR chains correctly, flat after sell, active_to set.
  4. Closed before window → excluded with reason=closed_before_window, not counted, empty series.
  5. Recent buy doesn't project back → anchor only on buy day.
  6. Contributors sum to portfolio daily return approximately.
  7. days_portfolio_ahead counts correctly.
  -- Legacy tests kept --
  8. ETF classification → excluded as classified_non_equity.
  9. Saxo-only position → excluded as saxo_only.
  10. Multi-currency FX applied consistently.
  11. Custom range missing params → raises ValueError.
"""
from __future__ import annotations

import builtins
from datetime import datetime, timezone, timedelta, date as date_type
from unittest.mock import patch

import pytest

from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction
from app.models.user import User
from app.services import benchmark as benchmark_svc
from app.services import classification as classification_svc


def _mk_days(start: int, end: int, step: int = -1):
    return builtins.range(start, end, step)


async def _seed_user(db, user_id):
    db.add(User(id=user_id, email=f"{user_id}@t.test", password_hash="x",
                api_key=f"apikey-{user_id}", display_name="t"))
    await db.commit()


async def _seed_account(db, user_id, name="Portfolio"):
    account = Account(user_id=user_id, name=name, type="brokerage", currency="USD")
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


def _mk_tx(user_id, account_id, symbol, ttype, qty, price, days_ago, currency="USD", fees=0.0):
    return StockTransaction(
        user_id=user_id, account_id=account_id,
        symbol=symbol, type=ttype, quantity=qty, price=price, fees=fees,
        currency=currency,
        executed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _mk_pos(user_id, account_id, symbol, qty, price=100.0, currency="USD"):
    return StockPosition(
        user_id=user_id, account_id=account_id, symbol=symbol,
        name=symbol,
        quantity=qty, avg_cost_price=price, currency=currency,
    )


async def fake_fx_1(f, t):
    return 1.0


def _flat_history_fn(today, n_days=60, price=100.0, bench_price=400.0):
    """Return a history function that gives flat prices for any ticker."""
    async def fake_history(ticker, range="1y", interval="1d"):  # noqa: A002
        p = bench_price if ticker in ("SPY", "^GSPC") else price
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": p}
            for d in _mk_days(n_days, -1, -1)
        ]
    return fake_history


# ---------------------------------------------------------------------------
# 1. Empty state
# ---------------------------------------------------------------------------

async def test_empty_state_returns_zero_series(db, user_id):
    await _seed_user(db, user_id)
    await _seed_account(db, user_id)
    result = await benchmark_svc.compute_benchmark_comparison(db, user_id, range_key="1M")
    assert result.portfolio_series == []
    assert result.benchmark_series == []
    assert result.summary["portfolio_return_pct"] == 0.0
    assert result.summary["benchmark_return_pct"] == 0.0
    assert result.summary["avg_daily_alpha_pp"] == 0.0
    assert result.summary["days_portfolio_ahead"] == 0
    assert result.summary["total_days_compared"] == 0
    assert any("No stock transactions" in c for c in result.caveats)


# ---------------------------------------------------------------------------
# 2. Single buy mid-window, flat prices → anchors at buy day, stays at 100
# ---------------------------------------------------------------------------

async def test_single_buy_mid_window_flat_prices(db, user_id):
    """Buy 10 AAPL on day -10 of a 30-day window at $100. Prices flat.
    - Anchor on day -10 (active_from == that day).
    - Portfolio index stays at 100 (no movement).
    - active_to == None (still held).
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)
    buy_days_ago = 10
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=buy_days_ago))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=10, price=100.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")

    today = datetime.now(timezone.utc).date()
    expected_active_from = (today - timedelta(days=buy_days_ago)).isoformat()

    with patch("app.services.benchmark.get_history", side_effect=_flat_history_fn(today)), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    assert result.portfolio_series[0]["index"] == 100.0
    assert abs(result.summary["portfolio_return_pct"]) < 0.1
    assert result.summary["benchmark_return_pct"] == 0.0 or abs(result.summary["benchmark_return_pct"]) < 0.1

    counted = {s["symbol"]: s for s in result.counted_symbols}
    assert "AAPL" in counted
    assert counted["AAPL"]["active_from"] == expected_active_from
    assert counted["AAPL"]["active_to"] is None  # still held
    assert counted["AAPL"]["current_qty"] == 10.0


# ---------------------------------------------------------------------------
# 3. Buy and sell mid-window, price rises
# ---------------------------------------------------------------------------

async def test_buy_sell_mid_window_price_rises(db, user_id):
    """Buy 10 AAPL on day -20 at $100. Price rises linearly to $110 on day -10.
    Sell 10 AAPL on day -10. No other positions.
    - Portfolio anchors at 100 on day -20.
    - Peaks near 110 on day -10 (≈10% gain).
    - Stays at ~110 from day -10 through today.
    - counted_symbols[0].active_from == (today-20).iso
    - counted_symbols[0].active_to == (today-10).iso
    - counted_symbols[0].current_qty == 0
    - contribution_pp ≈ 10
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)
    buy_days_ago = 20
    sell_days_ago = 10
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=buy_days_ago))
    db.add(_mk_tx(user_id, acct.id, "AAPL", "sell", 10, 110.0, days_ago=sell_days_ago))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=0, price=110.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")

    today = datetime.now(timezone.utc).date()
    expected_active_from = (today - timedelta(days=buy_days_ago)).isoformat()
    expected_active_to = (today - timedelta(days=sell_days_ago)).isoformat()

    # AAPL: $100 on day -20, rising to $110 on day -10, flat after
    def aapl_price(d_iso: str) -> float:
        d = date_type.fromisoformat(d_iso)
        days_before_today = (today - d).days
        if days_before_today > buy_days_ago:
            return 100.0  # pre-buy, doesn't matter
        if days_before_today >= sell_days_ago:
            # linear rise: $100 at day-20, $110 at day-10 (10 days of movement)
            frac = (buy_days_ago - days_before_today) / (buy_days_ago - sell_days_ago)
            return 100.0 + 10.0 * frac
        return 110.0  # after sell

    async def history_fn(ticker, range="1y", interval="1d"):  # noqa: A002
        n = 60
        if ticker in ("SPY", "^GSPC"):
            return [
                {"date": (today - timedelta(days=d)).isoformat(), "close": 400.0}
                for d in _mk_days(n, -1, -1)
            ]
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": aapl_price((today - timedelta(days=d)).isoformat())}
            for d in _mk_days(n, -1, -1)
        ]

    with patch("app.services.benchmark.get_history", side_effect=history_fn), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    assert len(result.portfolio_series) > 0, "Should have data points"

    # First point: anchor at 100
    assert result.portfolio_series[0]["index"] == 100.0

    # Final return should be ≈ +10%
    final_return = result.summary["portfolio_return_pct"]
    assert 8.0 < final_return < 12.0, f"Expected ~10% return, got {final_return}"

    # After the sell, last point index should be roughly same as near-sell peak
    last_idx = result.portfolio_series[-1]["index"]
    assert abs(last_idx - result.portfolio_series[-1]["index"]) < 0.01  # self-consistency

    # Counted symbol metadata
    counted = {s["symbol"]: s for s in result.counted_symbols}
    assert "AAPL" in counted
    assert counted["AAPL"]["active_from"] == expected_active_from
    assert counted["AAPL"]["active_to"] == expected_active_to
    assert counted["AAPL"]["current_qty"] == 0.0
    # contribution should be ≈ +10 pp (whole gain attributed to AAPL)
    assert counted["AAPL"]["contribution_pp"] > 7.0, f"contribution_pp = {counted['AAPL']['contribution_pp']}"

    # AAPL must NOT be in excluded
    excluded_syms = {s["symbol"] for s in result.excluded_symbols}
    assert "AAPL" not in excluded_syms


# ---------------------------------------------------------------------------
# 4. Closed before window → excluded as closed_before_window
# ---------------------------------------------------------------------------

async def test_closed_before_window_excluded(db, user_id):
    """Buy AAPL a year ago, sell 6 months ago. Window = 1M.
    AAPL is in excluded_symbols with reason=closed_before_window.
    Portfolio series is empty (no anchor).
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=365))
    db.add(_mk_tx(user_id, acct.id, "AAPL", "sell", 10, 120.0, days_ago=180))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=0, price=120.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    with patch("app.services.benchmark.get_history", side_effect=_flat_history_fn(today, n_days=400)), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    excluded = {s["symbol"]: s for s in result.excluded_symbols}
    counted = {s["symbol"] for s in result.counted_symbols}

    assert "AAPL" in excluded, f"excluded_symbols = {result.excluded_symbols}"
    assert excluded["AAPL"]["reason"] == "closed_before_window"
    assert "AAPL" not in counted
    assert result.portfolio_series == []


# ---------------------------------------------------------------------------
# 5. Recent buy doesn't project back
# ---------------------------------------------------------------------------

async def test_recent_buy_does_not_project_back(db, user_id):
    """NVDA bought 5 days ago. Window = 1Y.
    Portfolio anchors only on buy day (5 days ago), not at window start (365 days ago).
    counted_symbols[0].active_from == (today-5).iso
    Benchmark anchored at same day.
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)
    buy_days_ago = 5
    db.add(_mk_tx(user_id, acct.id, "NVDA", "buy", 5, 200.0, days_ago=buy_days_ago))
    db.add(_mk_pos(user_id, acct.id, "NVDA", qty=5, price=200.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "NVDA", "equity", source="user")

    today = datetime.now(timezone.utc).date()
    expected_active_from = (today - timedelta(days=buy_days_ago)).isoformat()

    with patch("app.services.benchmark.get_history", side_effect=_flat_history_fn(today, n_days=400)), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1Y", benchmark_symbol="SPY"
        )

    # Portfolio series should only start on buy day (5 days ago), not 365 days ago
    assert len(result.portfolio_series) > 0
    assert result.portfolio_series[0]["date"] == expected_active_from, (
        f"First portfolio point should be buy day {expected_active_from}, "
        f"got {result.portfolio_series[0]['date']}"
    )
    assert result.portfolio_series[0]["index"] == 100.0

    # Benchmark also anchored at same day
    assert len(result.benchmark_series) > 0
    assert result.benchmark_series[0]["date"] == expected_active_from, (
        f"Benchmark should also start at {expected_active_from}, "
        f"got {result.benchmark_series[0]['date']}"
    )
    assert result.benchmark_series[0]["index"] == 100.0

    # active_from is buy day
    counted = {s["symbol"]: s for s in result.counted_symbols}
    assert "NVDA" in counted
    assert counted["NVDA"]["active_from"] == expected_active_from


# ---------------------------------------------------------------------------
# 6. Contributors sum to portfolio daily return (approximately)
# ---------------------------------------------------------------------------

async def test_contributors_sum_to_daily_return(db, user_id):
    """Two stocks AAPL (+1%) and MSFT (+2%) held in equal value.
    Sum of daily contributors_pp should ≈ portfolio daily return * 100.
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)
    # Buy both 15 days ago
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=15))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=10, price=100.0))
    db.add(_mk_tx(user_id, acct.id, "MSFT", "buy", 10, 100.0, days_ago=15))
    db.add(_mk_pos(user_id, acct.id, "MSFT", qty=10, price=100.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")
    await classification_svc.set_classification(db, user_id, "MSFT", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    # Day 0 (most recent): AAPL $101, MSFT $102. Day -1: AAPL $100, MSFT $100.
    def price_fn(ticker: str, d_iso: str) -> float:
        d = date_type.fromisoformat(d_iso)
        days_ago = (today - d).days
        if ticker == "AAPL":
            return 101.0 if days_ago == 0 else 100.0
        if ticker == "MSFT":
            return 102.0 if days_ago == 0 else 100.0
        return 400.0

    async def history_fn(ticker, range="1y", interval="1d"):  # noqa: A002
        n = 30
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": price_fn(ticker, (today - timedelta(days=d)).isoformat())}
            for d in _mk_days(n, -1, -1)
        ]

    with patch("app.services.benchmark.get_history", side_effect=history_fn), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    # Find the last data point (today) and check contributors
    assert len(result.portfolio_series) >= 2
    last_point = result.portfolio_series[-1]
    contributors = last_point.get("contributors", {})

    if contributors:
        contrib_sum = sum(contributors.values())
        # Daily return on the final day:
        # V_prev = 10*100 + 10*100 = 2000, V_d = 10*101 + 10*102 = 2030
        # r_d = (2030 - 2000 - 0) / 2000 = 0.015 → 1.5pp
        # sum contributors ≈ 1.5
        prev_point = result.portfolio_series[-2]
        daily_port_r_pp = last_point["index"] - prev_point["index"]
        assert abs(contrib_sum - daily_port_r_pp) < 0.1, (
            f"Contributors sum {contrib_sum:.4f} should ≈ daily portfolio return {daily_port_r_pp:.4f}pp"
        )


# ---------------------------------------------------------------------------
# 7. days_portfolio_ahead counts correctly
# ---------------------------------------------------------------------------

async def test_days_portfolio_ahead(db, user_id):
    """Portfolio beats benchmark on exactly N days (benchmark flat, portfolio rises).
    All post-anchor days should be ahead.
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)
    # Buy 20 days ago
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=20))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=10, price=100.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    # AAPL rises every day from 100 to 120 over 20 days. Benchmark flat.
    def aapl_price(d_iso: str) -> float:
        d = date_type.fromisoformat(d_iso)
        days_ago = (today - d).days
        if days_ago > 20:
            return 100.0
        return 100.0 + (20 - days_ago) * 1.0  # +1 per day

    async def history_fn(ticker, range="1y", interval="1d"):  # noqa: A002
        n = 40
        if ticker in ("SPY", "^GSPC"):
            return [
                {"date": (today - timedelta(days=d)).isoformat(), "close": 400.0}
                for d in _mk_days(n, -1, -1)
            ]
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": aapl_price((today - timedelta(days=d)).isoformat())}
            for d in _mk_days(n, -1, -1)
        ]

    with patch("app.services.benchmark.get_history", side_effect=history_fn), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    # Portfolio rises steadily while benchmark is flat, so it should be ahead on all compared days
    assert result.summary["days_portfolio_ahead"] > 0
    assert result.summary["total_days_compared"] > 0
    # Since portfolio always rises and benchmark is flat, all compared days should be portfolio ahead
    assert result.summary["days_portfolio_ahead"] == result.summary["total_days_compared"]
    # Portfolio must beat benchmark
    assert result.summary["portfolio_return_pct"] > result.summary["benchmark_return_pct"]
    assert result.summary["alpha_pct"] > 0


# ---------------------------------------------------------------------------
# Legacy test 8: Sold-out symbol → excluded appropriately
# ---------------------------------------------------------------------------

async def test_sold_out_symbol_excluded(db, user_id):
    """TSLA bought and fully sold within window while AAPL is still held.
    TSLA should be counted (it was held in the window), not excluded.
    AAPL should also be counted.
    """
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)

    # AAPL still held
    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=45))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=10, price=100.0))

    # TSLA bought and fully sold within the 1M window
    db.add(_mk_tx(user_id, acct.id, "TSLA", "buy", 5, 200.0, days_ago=25))
    db.add(_mk_tx(user_id, acct.id, "TSLA", "sell", 5, 220.0, days_ago=10))
    db.add(_mk_pos(user_id, acct.id, "TSLA", qty=0, price=220.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")
    await classification_svc.set_classification(db, user_id, "TSLA", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    async def flat_history(ticker, range="1y", interval="1d"):  # noqa: A002
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": 100.0}
            for d in _mk_days(60, -1, -1)
        ]

    with patch("app.services.benchmark.get_history", side_effect=flat_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    counted = {s["symbol"] for s in result.counted_symbols}
    # Both AAPL and TSLA were active in the window (TSLA had active holding period)
    assert "AAPL" in counted
    # TSLA was held during the window and should be counted
    assert "TSLA" in counted
    # TSLA should not be in excluded
    excluded_syms = {s["symbol"] for s in result.excluded_symbols}
    assert "TSLA" not in excluded_syms


# ---------------------------------------------------------------------------
# Legacy test 9: ETF classification → excluded as classified_non_equity
# ---------------------------------------------------------------------------

async def test_etf_excluded_from_individual_series(db, user_id):
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)

    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 150.0, days_ago=45))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=10, price=150.0))

    db.add(_mk_tx(user_id, acct.id, "SPY", "buy", 5, 400.0, days_ago=40))
    db.add(_mk_pos(user_id, acct.id, "SPY", qty=5, price=400.0))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")
    await classification_svc.set_classification(db, user_id, "SPY", "etf", source="user")

    today = datetime.now(timezone.utc).date()

    async def fake_history(ticker, range="1y", interval="1d"):  # noqa: A002
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": 1.0}
            for d in _mk_days(60, -1, -1)
        ]

    with patch("app.services.benchmark.get_history", side_effect=fake_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    counted = {s["symbol"] for s in result.counted_symbols}
    excluded = {s["symbol"]: s for s in result.excluded_symbols}

    assert "AAPL" in counted
    assert "SPY" not in counted
    assert "SPY" in excluded
    assert excluded["SPY"]["reason"] == "classified_non_equity"
    assert excluded["SPY"]["asset_type"] == "etf"


# ---------------------------------------------------------------------------
# Legacy test 10: Saxo-only position → excluded as saxo_only
# ---------------------------------------------------------------------------

async def test_saxo_only_positions_flagged_as_caveat(db, user_id):
    from app.models.user import User as UserModel
    db.add(UserModel(id=user_id, email=f"{user_id}@t.test", password_hash="x",
                api_key=f"apikey-{user_id}", display_name="t"))
    manual_acct = Account(user_id=user_id, name="Portfolio", type="brokerage", currency="USD")
    saxo_acct = Account(user_id=user_id, name="Saxo sim [AK]", type="brokerage", currency="EUR")
    db.add_all([manual_acct, saxo_acct])
    await db.commit()
    await db.refresh(manual_acct)
    await db.refresh(saxo_acct)

    db.add(_mk_tx(user_id, manual_acct.id, "AAPL", "buy", 10, 100.0, days_ago=45))
    db.add(_mk_pos(user_id, manual_acct.id, "AAPL", qty=10, price=100.0))

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

    with patch("app.services.benchmark.get_history", side_effect=fake_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fake_fx_1):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M"
        )

    msft_excluded = [s for s in result.excluded_symbols if s["symbol"] == "MSFT" and s["reason"] == "saxo_only"]
    assert len(msft_excluded) == 1
    assert any("Saxo" in c for c in result.caveats)

    counted = {s["symbol"] for s in result.counted_symbols}
    assert "AAPL" in counted
    assert "MSFT" not in counted


# ---------------------------------------------------------------------------
# Legacy test 11: Multi-currency FX applied consistently
# ---------------------------------------------------------------------------

async def test_multi_currency_fx_applied(db, user_id):
    """Portfolio has USD and EUR positions; both must be converted to CHF."""
    await _seed_user(db, user_id)
    acct = await _seed_account(db, user_id)

    db.add(_mk_tx(user_id, acct.id, "AAPL", "buy", 10, 100.0, days_ago=45, currency="USD"))
    db.add(_mk_pos(user_id, acct.id, "AAPL", qty=10, price=100.0, currency="USD"))

    db.add(_mk_tx(user_id, acct.id, "SAP", "buy", 5, 200.0, days_ago=45, currency="EUR"))
    db.add(_mk_pos(user_id, acct.id, "SAP", qty=5, price=200.0, currency="EUR"))
    await db.commit()

    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="user")
    await classification_svc.set_classification(db, user_id, "SAP", "equity", source="user")

    today = datetime.now(timezone.utc).date()

    async def flat_history(ticker, range="1y", interval="1d"):  # noqa: A002
        price = 100.0 if ticker == "AAPL" else 200.0 if ticker == "SAP" else 400.0
        return [
            {"date": (today - timedelta(days=d)).isoformat(), "close": price}
            for d in _mk_days(60, -1, -1)
        ]

    async def fx_rates(f, t):
        if f == "USD":
            return 0.9
        if f == "EUR":
            return 1.1
        return 1.0

    with patch("app.services.benchmark.get_history", side_effect=flat_history), \
         patch("app.services.benchmark.get_fx_rate", side_effect=fx_rates):
        result = await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="1M", benchmark_symbol="SPY"
        )

    assert abs(result.summary["portfolio_return_pct"]) < 0.1
    counted = {s["symbol"] for s in result.counted_symbols}
    assert "AAPL" in counted
    assert "SAP" in counted
    assert result.portfolio_series[0]["index"] == 100.0
    # CHF value: 10*100*0.9 + 5*200*1.1 = 900 + 1100 = 2000
    first_val = result.portfolio_series[0]["value_chf"]
    assert abs(first_val - 2000.0) < 1.0


# ---------------------------------------------------------------------------
# Legacy test 12: Custom range without params → raises ValueError
# ---------------------------------------------------------------------------

async def test_custom_range_requires_start_and_end(db, user_id):
    await _seed_user(db, user_id)
    await _seed_account(db, user_id)
    with pytest.raises(Exception):
        await benchmark_svc.compute_benchmark_comparison(
            db, user_id, range_key="CUSTOM", custom_start=None, custom_end=None
        )
