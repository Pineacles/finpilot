"""GET/POST/DELETE /api/dashboard/watchlist — endpoint-level: duplicate
add must 409, invalid symbol must 400, delete of unknown symbol must 404.
Endpoint handlers are called directly (no HTTP transport), matching the
pattern in tests/brokers/test_saxo_sub_portfolio.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.endpoints.watchlist import (
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    WatchlistAddRequest,
)

_QUOTE = {"price": 250.0, "currency": "USD", "name": "Tesla Inc.", "change": 5.0, "change_pct": 2.0}


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id


async def test_add_list_delete_roundtrip(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=_QUOTE):
        added = await add_to_watchlist(WatchlistAddRequest(symbol="tsla"), user=FakeUser(user_id), db=db)
        assert added["symbol"] == "TSLA"

        listed = await get_watchlist(user=FakeUser(user_id), db=db)
        assert len(listed) == 1

        await remove_from_watchlist("TSLA", user=FakeUser(user_id), db=db)
        listed_after = await get_watchlist(user=FakeUser(user_id), db=db)
    assert listed_after == []


async def test_add_duplicate_returns_409(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=_QUOTE):
        await add_to_watchlist(WatchlistAddRequest(symbol="TSLA"), user=FakeUser(user_id), db=db)
        with pytest.raises(HTTPException) as exc_info:
            await add_to_watchlist(WatchlistAddRequest(symbol="TSLA"), user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 409


async def test_add_invalid_symbol_returns_400(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await add_to_watchlist(WatchlistAddRequest(symbol="NOTATICKER"), user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 400


async def test_delete_unknown_symbol_returns_404(db, user_id):
    with pytest.raises(HTTPException) as exc_info:
        await remove_from_watchlist("GHOST", user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 404
