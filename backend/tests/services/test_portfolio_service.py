"""portfolio_service: honesty guarantees — no silent stale prices, no silent
FX=1.0, no silent currency overwrite on trade entry.

These replace the old behavior where:
  - a failed yfinance quote fetch was invisibly masked (last_price_at bumped
    to "now" regardless of whether the fetch actually succeeded)
  - a failed FX lookup silently defaulted to 1.0, corrupting CHF totals
  - a trade's user-supplied currency was silently overwritten by yfinance's
    quote currency
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.account import Account
from app.models.stock import StockPosition
from app.services import portfolio_service
from app.services.portfolio_service import CurrencyMismatchError, FxRateUnavailableError


async def _make_brokerage(db, user_id: str) -> Account:
    acct = Account(user_id=user_id, name="Portfolio", type="brokerage", currency="USD")
    db.add(acct)
    await db.flush()
    return acct


async def _make_position(
    db, user_id: str, account_id: str, *, symbol="AAPL", currency="USD",
    quantity=10, avg_cost=90.0, last_price=100.0, last_price_at=None,
) -> StockPosition:
    pos = StockPosition(
        user_id=user_id, account_id=account_id, symbol=symbol, name=symbol,
        quantity=quantity, avg_cost_price=avg_cost, currency=currency,
        last_price=last_price, last_price_at=last_price_at,
    )
    db.add(pos)
    await db.flush()
    return pos


# ── Quote fetch failure → warnings + honest staleness ─────────────────────

async def test_quote_fetch_failure_populates_warning_and_marks_stale(db, user_id):
    acct = await _make_brokerage(db, user_id)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    await _make_position(db, user_id, acct.id, last_price_at=old_time)
    await db.commit()

    with patch("app.services.portfolio_service.get_quotes_batch", return_value={}), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=0.9):
        result = await portfolio_service.get_portfolio(db, user_id)

    assert any("AAPL" in w for w in result["warnings"])
    pos = result["positions"][0]
    assert pos["price_stale"] is True


async def test_quote_fetch_failure_within_threshold_not_flagged_stale(db, user_id):
    """A failed fetch this request still produces a warning, but the
    staleness *badge* only lights up once the last known price is >15min
    old — a failure two minutes ago with a fresh-enough cached price
    shouldn't cry wolf."""
    acct = await _make_brokerage(db, user_id)
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    await _make_position(db, user_id, acct.id, last_price_at=recent_time)
    await db.commit()

    with patch("app.services.portfolio_service.get_quotes_batch", return_value={}), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=0.9):
        result = await portfolio_service.get_portfolio(db, user_id)

    assert any("AAPL" in w for w in result["warnings"])
    assert result["positions"][0]["price_stale"] is False


async def test_successful_quote_fetch_does_not_warn_or_stale(db, user_id):
    acct = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, acct.id)
    await db.commit()

    fresh_quote = {"price": 105.0, "currency": "USD", "name": "Apple", "change": 1.0, "change_pct": 1.0, "quote_fetch_failed": False}
    with patch("app.services.portfolio_service.get_quotes_batch", return_value={"AAPL": fresh_quote}), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=0.9):
        result = await portfolio_service.get_portfolio(db, user_id)

    assert result["warnings"] == []
    assert result["positions"][0]["price_stale"] is False
    assert result["positions"][0]["last_price"] == 105.0


# ── FX failure → never silently 1.0 ───────────────────────────────────────

async def test_fx_failure_falls_back_to_cached_rate_with_warning(db, user_id):
    acct = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, acct.id, last_price=100.0, avg_cost=100.0, quantity=1)
    await db.commit()

    quote = {"price": 100.0, "currency": "USD", "name": "Apple", "change": 0, "change_pct": 0, "quote_fetch_failed": False}
    with patch("app.services.portfolio_service.get_quotes_batch", return_value={"AAPL": quote}), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=None), \
         patch("app.services.portfolio_service.get_cached_fx_rate", return_value=0.95):
        result = await portfolio_service.get_portfolio(db, user_id)

    assert any("last known" in w.lower() for w in result["warnings"])
    pos = result["positions"][0]
    assert pos["fx_unavailable"] is False
    assert pos["market_value"] == pytest.approx(100.0 * 0.95)


async def test_fx_failure_with_no_cache_excludes_position_from_totals(db, user_id):
    acct = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, acct.id, last_price=100.0, avg_cost=100.0, quantity=1)
    await db.commit()

    quote = {"price": 100.0, "currency": "USD", "name": "Apple", "change": 0, "change_pct": 0, "quote_fetch_failed": False}
    with patch("app.services.portfolio_service.get_quotes_batch", return_value={"AAPL": quote}), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=None), \
         patch("app.services.portfolio_service.get_cached_fx_rate", return_value=None):
        result = await portfolio_service.get_portfolio(db, user_id)

    assert any("AAPL" in w and "excluded" in w for w in result["warnings"])
    pos = result["positions"][0]
    assert pos["fx_unavailable"] is True
    assert pos["market_value"] == 0.0
    # Excluded position must not silently contribute to CHF totals either.
    assert result["total_value"] == 0.0


# ── execute_trade: currency mismatch never silently overwritten ──────────

async def test_execute_trade_rejects_currency_mismatch_without_confirm(db, user_id):
    quote = {"price": 10.0, "currency": "GBP", "name": "Vodafone"}
    with patch("app.services.portfolio_service.get_quote", return_value=quote):
        with pytest.raises(CurrencyMismatchError) as exc_info:
            await portfolio_service.execute_trade(
                db, user_id, symbol="VOD", type="buy", quantity=1,
                currency="USD", deduct_from_cash=False,
            )
    assert exc_info.value.user_currency == "USD"
    assert exc_info.value.quote_currency == "GBP"
    assert exc_info.value.ticker == "VOD"


async def test_execute_trade_confirm_currency_uses_quote_currency(db, user_id):
    quote = {"price": 10.0, "currency": "GBP", "name": "Vodafone"}
    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.15):
        result = await portfolio_service.execute_trade(
            db, user_id, symbol="VOD", type="buy", quantity=1,
            currency="USD", deduct_from_cash=False, confirm_currency=True,
        )
    assert result["currency"] == "GBP"


async def test_execute_trade_raises_when_fx_unavailable(db, user_id):
    quote = {"price": 10.0, "currency": "USD", "name": "Test Co"}
    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=None):
        with pytest.raises(FxRateUnavailableError):
            await portfolio_service.execute_trade(
                db, user_id, symbol="TEST", type="buy", quantity=1,
                currency="USD", deduct_from_cash=False,
            )
