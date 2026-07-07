"""Watchlist — selective stock tracking with NO analysis or recommendations.

Shared between the JWT-authenticated dashboard router (watchlist.py) and the
API-key agent router (agent_portfolio_router.py) so both surfaces stay in
sync. Just live price + day change; nothing predictive.
"""
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist import WatchlistItem
from app.services.prices import get_quote


class WatchlistDuplicateError(Exception):
    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"{symbol} is already on the watchlist")


class WatchlistInvalidSymbolError(Exception):
    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"No fetchable quote for {symbol}")


class WatchlistItemNotFoundError(Exception):
    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"{symbol} is not on the watchlist")


def _shape_item(item: WatchlistItem, quote: dict | None) -> dict:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "price": quote.get("price") if quote else None,
        "change": quote.get("change") if quote else None,
        "change_pct": quote.get("change_pct") if quote else None,
        "currency": quote.get("currency") if quote else None,
        "name": quote.get("name") if quote else None,
        "quote_unavailable": quote is None,
    }


async def list_watchlist(db: AsyncSession, user_id: str) -> list[dict]:
    result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == user_id).order_by(WatchlistItem.added_at)
    )
    items = list(result.scalars().all())
    out = []
    for item in items:
        quote = await get_quote(item.symbol)
        out.append(_shape_item(item, quote))
    return out


async def add_watchlist_item(db: AsyncSession, user_id: str, symbol: str) -> dict:
    ticker = symbol.upper().strip()

    existing = await db.execute(
        select(WatchlistItem).where(and_(WatchlistItem.user_id == user_id, WatchlistItem.symbol == ticker))
    )
    if existing.scalar_one_or_none():
        raise WatchlistDuplicateError(ticker)

    quote = await get_quote(ticker)
    if not quote:
        raise WatchlistInvalidSymbolError(ticker)

    item = WatchlistItem(user_id=user_id, symbol=ticker, added_at=datetime.now(timezone.utc))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _shape_item(item, quote)


async def remove_watchlist_item(db: AsyncSession, user_id: str, symbol_or_id: str) -> None:
    result = await db.execute(
        select(WatchlistItem).where(and_(
            WatchlistItem.user_id == user_id,
            (WatchlistItem.id == symbol_or_id) | (WatchlistItem.symbol == symbol_or_id.upper().strip()),
        ))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise WatchlistItemNotFoundError(symbol_or_id)
    await db.delete(item)
    await db.commit()
