"""portfolio_service: honesty guarantees. No silent stale prices, no silent
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
from app.services import classification, portfolio_service
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
    old: a failure two minutes ago with a fresh-enough cached price
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


# ── "private" positions: permanently unpriceable, never warn ─────────────

async def test_private_position_never_fetches_quote_or_warns(db, user_id):
    acct = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, acct.id, symbol="SPACEX", currency="USD", quantity=1, last_price=50.0)
    await db.commit()
    await classification.set_classification(db, user_id, "SPACEX", "private", "user")

    async def _spy_quotes_batch(tickers):
        raise AssertionError(f"should not be called, got tickers={tickers}")

    with patch("app.services.portfolio_service.get_quotes_batch", _spy_quotes_batch), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.0):
        result = await portfolio_service.get_portfolio(db, user_id)

    assert result["warnings"] == []
    pos = result["positions"][0]
    assert pos["symbol"] == "SPACEX"
    assert pos["manual_price"] is True
    assert pos["market_value"] == pytest.approx(50.0)  # last_price * quantity(1), unchanged


async def test_private_position_excluded_from_failed_symbols_alongside_normal_position(db, user_id):
    acct = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, acct.id, symbol="AAPL")
    await _make_position(db, user_id, acct.id, symbol="SPACEX", currency="USD", last_price=50.0)
    await db.commit()
    await classification.set_classification(db, user_id, "SPACEX", "private", "user")

    with patch("app.services.portfolio_service.get_quotes_batch", return_value={}) as mock_batch, \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.0):
        result = await portfolio_service.get_portfolio(db, user_id)

    called_tickers = mock_batch.call_args[0][0]
    assert "SPACEX" not in called_tickers
    assert "AAPL" in called_tickers

    assert any("AAPL" in w for w in result["warnings"])
    assert all("SPACEX" not in w for w in result["warnings"])

    by_symbol = {p["symbol"]: p for p in result["positions"]}
    assert by_symbol["SPACEX"]["manual_price"] is True
    assert by_symbol["AAPL"]["manual_price"] is False


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


# ── execute_trade: new positions get classified, without ever failing ────

async def test_execute_trade_buy_new_position_classifies_ticker(db, user_id, monkeypatch):
    quote = {"price": 10.0, "currency": "USD", "name": "Test Co"}
    called = {}

    async def _fake_ensure_classified(db_arg, user_id_arg, symbol):
        called["symbol"] = symbol

    monkeypatch.setattr(classification, "ensure_classified", _fake_ensure_classified)

    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.0):
        await portfolio_service.execute_trade(
            db, user_id, symbol="TEST", type="buy", quantity=1,
            currency="USD", deduct_from_cash=False,
        )

    assert called["symbol"] == "TEST"


async def test_execute_trade_buy_existing_position_does_not_reclassify(db, user_id, monkeypatch):
    quote = {"price": 10.0, "currency": "USD", "name": "Test Co"}

    async def _must_not_be_called(*args, **kwargs):
        raise AssertionError("should not be called for an existing position")

    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.0):
        await portfolio_service.execute_trade(
            db, user_id, symbol="TEST", type="buy", quantity=1,
            currency="USD", deduct_from_cash=False,
        )

        monkeypatch.setattr(classification, "ensure_classified", _must_not_be_called)
        await portfolio_service.execute_trade(
            db, user_id, symbol="TEST", type="buy", quantity=1,
            currency="USD", deduct_from_cash=False,
        )


async def test_execute_trade_buy_classification_failure_does_not_fail_trade(db, user_id, monkeypatch):
    quote = {"price": 10.0, "currency": "USD", "name": "Test Co"}

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(classification, "ensure_classified", _raise)

    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.0):
        result = await portfolio_service.execute_trade(
            db, user_id, symbol="TEST", type="buy", quantity=1,
            currency="USD", deduct_from_cash=False,
        )

    assert result["status"] == "ok"


# ── compute_total_wealth: positions + cash + bank balance ────────────────

async def test_compute_total_wealth_sums_positions_cash_and_bank_balance(db, user_id):
    from datetime import date as _date

    from app.models.finance import Transaction

    brokerage = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, brokerage.id, symbol="AAPL", quantity=10, avg_cost=90.0, last_price=100.0)
    await _make_position(db, user_id, brokerage.id, symbol="CASH", quantity=250.0, avg_cost=1.0, last_price=None)

    bank = Account(user_id=user_id, name="Bank", type="bank", currency="CHF")
    db.add(bank)
    await db.flush()
    db.add_all([
        Transaction(user_id=user_id, account_id=bank.id, date=_date(2026, 1, 5), merchant="Employer", amount=3000.0, currency="CHF"),
        Transaction(user_id=user_id, account_id=bank.id, date=_date(2026, 1, 10), merchant="Rent", amount=-1200.0, currency="CHF"),
    ])
    await db.commit()

    total = await portfolio_service.compute_total_wealth(db, user_id)

    # AAPL: 10 * 100.0 = 1000.0, CASH position: 250.0, bank balance: 3000 - 1200 = 1800.0
    assert total == 1000.0 + 250.0 + 1800.0


async def test_compute_total_wealth_falls_back_to_avg_cost_without_live_price(db, user_id):
    brokerage = await _make_brokerage(db, user_id)
    await _make_position(db, user_id, brokerage.id, symbol="MSFT", quantity=5, avg_cost=80.0, last_price=None)
    await db.commit()

    total = await portfolio_service.compute_total_wealth(db, user_id)

    assert total == 5 * 80.0
