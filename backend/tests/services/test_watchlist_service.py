"""watchlist_service: tracking-only symbol list — CRUD + duplicate rejection.

No AI analysis/recommendations here by design (see redesign decisions) —
just live price + day change, mirroring what the endpoint exposes.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import watchlist_service
from app.services.watchlist_service import (
    WatchlistDuplicateError,
    WatchlistInvalidSymbolError,
    WatchlistItemNotFoundError,
)

_QUOTE = {"price": 250.0, "currency": "USD", "name": "Tesla Inc.", "change": 5.0, "change_pct": 2.0}


async def test_add_and_list_watchlist_item(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=_QUOTE):
        added = await watchlist_service.add_watchlist_item(db, user_id, "tsla")
        assert added["symbol"] == "TSLA"
        assert added["price"] == 250.0
        assert added["change_pct"] == 2.0
        assert added["quote_unavailable"] is False

        items = await watchlist_service.list_watchlist(db, user_id)
    assert len(items) == 1
    assert items[0]["symbol"] == "TSLA"


async def test_add_duplicate_symbol_rejected(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=_QUOTE):
        await watchlist_service.add_watchlist_item(db, user_id, "TSLA")
        with pytest.raises(WatchlistDuplicateError):
            await watchlist_service.add_watchlist_item(db, user_id, "TSLA")


async def test_add_invalid_symbol_rejected(db, user_id):
    """POST must validate the symbol has a fetchable quote before adding."""
    with patch("app.services.watchlist_service.get_quote", return_value=None):
        with pytest.raises(WatchlistInvalidSymbolError):
            await watchlist_service.add_watchlist_item(db, user_id, "NOTATICKER")


async def test_remove_by_symbol(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=_QUOTE):
        await watchlist_service.add_watchlist_item(db, user_id, "TSLA")
        await watchlist_service.remove_watchlist_item(db, user_id, "TSLA")
        items = await watchlist_service.list_watchlist(db, user_id)
    assert items == []


async def test_remove_nonexistent_raises(db, user_id):
    with pytest.raises(WatchlistItemNotFoundError):
        await watchlist_service.remove_watchlist_item(db, user_id, "GHOST")


async def test_watchlist_scoped_per_user(db, user_id):
    with patch("app.services.watchlist_service.get_quote", return_value=_QUOTE):
        await watchlist_service.add_watchlist_item(db, user_id, "TSLA")
        other_items = await watchlist_service.list_watchlist(db, "some-other-user")
    assert other_items == []
