"""Public portfolio sharing endpoints: unauthenticated read-only views."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot
from app.models.user import User
from app.services.prices import get_quotes_batch, get_history
from app.services import portfolio_service
from app.services.portfolio_service import build_value_timeline

# ── Public portfolio view (no auth) ────────────────────────────

public_router = APIRouter(prefix="/api/public", tags=["public"])


async def _lookup_public_user(db: AsyncSession, token: str) -> User:
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return user


@public_router.get("/portfolio/{token}")
async def get_public_portfolio(token: str, db: AsyncSession = Depends(get_db)):
    """Mirrors the private dashboard's valuation logic exactly (same
    honesty guarantees: no silent FX=1.0, staleness/warnings surfaced) via
    portfolio_service.get_public_portfolio; this router only resolves the
    share token and adds the display name."""
    user = await _lookup_public_user(db, token)
    data = await portfolio_service.get_public_portfolio(db, user.id)
    return {"display_name": user.display_name, **data}


@public_router.get("/portfolio/{token}/chart/{ticker}")
async def get_public_chart(token: str, ticker: str, range: str = "1y", interval: str | None = None, db: AsyncSession = Depends(get_db)):
    """Public price chart. Validates the share token first."""
    await _lookup_public_user(db, token)
    valid_ranges = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}
    if range not in valid_ranges:
        raise HTTPException(status_code=400, detail="Invalid range")
    # Auto-select interval if not explicitly provided so 1D/1W show intraday detail
    if interval is None:
        if range == "1d":
            interval = "5m"
        elif range == "5d":
            interval = "30m"
        else:
            interval = "1d"
    data = await get_history(ticker, range=range, interval=interval)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return {"ticker": ticker, "range": range, "data": data}


@public_router.get("/portfolio/{token}/trades")
async def get_public_trades(token: str, symbol: str | None = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Public trade history. Validates the share token first."""
    user = await _lookup_public_user(db, token)

    query = select(StockTransaction).where(StockTransaction.user_id == user.id)
    if symbol:
        query = query.where(StockTransaction.symbol == symbol.upper())
    query = query.order_by(desc(StockTransaction.executed_at)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    fx = await portfolio_service.get_fx_rates_for_trades(trades, base="CHF")

    return [
        {
            "id": t.id, "symbol": t.symbol, "type": t.type,
            "quantity": t.quantity, "price": t.price, "fees": t.fees,
            "currency": t.currency, "date": t.executed_at.isoformat(),
            "total": t.quantity * t.price,
            "total_chf": round((t.quantity * t.price) * fx.get(t.currency, 1.0), 2),
            "fees_chf": round(t.fees * fx.get(t.currency, 1.0), 2),
        }
        for t in trades
    ]


@public_router.get("/portfolio/{token}/live-prices")
async def get_public_live_prices(token: str, db: AsyncSession = Depends(get_db)):
    """Public lightweight live prices for held positions."""
    user = await _lookup_public_user(db, token)

    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user.id,
            StockPosition.symbol != "CASH",
            StockPosition.quantity > 0,
        ))
    )
    positions = result.scalars().all()
    if not positions:
        return {}

    tickers = list({p.symbol for p in positions})
    quotes = await get_quotes_batch(tickers, cache_ttl=15)

    return {
        sym: {
            "price": q["price"],
            "change": q.get("change", 0),
            "change_pct": q.get("change_pct", 0),
        }
        for sym, q in quotes.items()
    }


@public_router.get("/portfolio/{token}/value-timeline")
async def get_public_value_timeline(token: str, db: AsyncSession = Depends(get_db)):
    """Public portfolio value timeline built from transactions + yfinance."""
    user = await _lookup_public_user(db, token)
    return await build_value_timeline(db, user.id)


@public_router.get("/portfolio/{token}/history")
async def get_public_portfolio_history(token: str, days: int = 365, db: AsyncSession = Depends(get_db)):
    """Public portfolio value history."""
    user = await _lookup_public_user(db, token)

    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(and_(PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.snapshot_date >= since))
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    return [{"date": s.snapshot_date.isoformat(), "value": s.total_value, "pnl": s.total_pnl} for s in result.scalars().all()]


