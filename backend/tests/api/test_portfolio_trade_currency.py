"""GET/POST /api/dashboard/portfolio/trade: currency mismatch must reject
with 422 (naming both currencies + a suggested ticker) unless the caller
sets confirm_currency=true. We call the endpoint handler directly (same
pattern as tests/brokers/test_saxo_sub_portfolio.py) to exercise the full
router -> service -> HTTPException mapping without HTTP transport overhead.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.endpoints.portfolio import execute_trade as trade_endpoint, TradeRequest


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id


async def test_currency_mismatch_returns_422_with_suggestion(db, user_id):
    quote = {"price": 10.0, "currency": "GBP", "name": "Vodafone"}
    body = TradeRequest(symbol="VOD", type="buy", quantity=1, currency="USD", deduct_from_cash=False)

    with patch("app.services.portfolio_service.get_quote", return_value=quote):
        with pytest.raises(HTTPException) as exc_info:
            await trade_endpoint(body=body, user=FakeUser(user_id), db=db)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["error"] == "currency_mismatch"
    assert detail["user_currency"] == "USD"
    assert detail["quote_currency"] == "GBP"
    assert detail["suggested_ticker"] == "VOD.L"
    assert "USD" in detail["message"] and "GBP" in detail["message"]


async def test_confirm_currency_true_proceeds_with_quote_currency(db, user_id):
    quote = {"price": 10.0, "currency": "GBP", "name": "Vodafone"}
    body = TradeRequest(
        symbol="VOD", type="buy", quantity=1, currency="USD",
        deduct_from_cash=False, confirm_currency=True,
    )

    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=1.15):
        result = await trade_endpoint(body=body, user=FakeUser(user_id), db=db)

    assert result["status"] == "ok"
    assert result["currency"] == "GBP"


async def test_matching_currency_does_not_raise(db, user_id):
    """No mismatch at all: regular happy path, no 422."""
    quote = {"price": 10.0, "currency": "USD", "name": "Test Co"}
    body = TradeRequest(symbol="TEST", type="buy", quantity=1, currency="USD", deduct_from_cash=False)

    with patch("app.services.portfolio_service.get_quote", return_value=quote), \
         patch("app.services.portfolio_service.get_fx_rate", return_value=0.9):
        result = await trade_endpoint(body=body, user=FakeUser(user_id), db=db)

    assert result["status"] == "ok"
    assert result["currency"] == "USD"
