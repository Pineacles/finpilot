"""Watchlist endpoints — tracking-only, no AI analysis or recommendations.

Business logic lives in app.services.watchlist_service so the dashboard
(JWT) and agent (API key) surfaces share the same behavior.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import watchlist_service
from app.services.watchlist_service import (
    WatchlistDuplicateError,
    WatchlistInvalidSymbolError,
    WatchlistItemNotFoundError,
)
from app.schemas.watchlist import WatchlistItemOut

router = APIRouter(prefix="/api/dashboard/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    symbol: str


@router.get("", response_model=list[WatchlistItemOut])
async def get_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await watchlist_service.list_watchlist(db, user.id)


@router.post("", response_model=WatchlistItemOut)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await watchlist_service.add_watchlist_item(db, user.id, body.symbol)
    except WatchlistDuplicateError as e:
        raise HTTPException(status_code=409, detail=f"{e.symbol} is already on your watchlist")
    except WatchlistInvalidSymbolError as e:
        raise HTTPException(status_code=400, detail=f"No live quote found for {e.symbol} — check the ticker")


@router.delete("/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await watchlist_service.remove_watchlist_item(db, user.id, symbol)
    except WatchlistItemNotFoundError:
        raise HTTPException(status_code=404, detail=f"{symbol} is not on your watchlist")
    return {"status": "ok"}
