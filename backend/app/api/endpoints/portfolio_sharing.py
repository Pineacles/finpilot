"""Public portfolio sharing endpoints — unauthenticated read-only views."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot
from app.models.user import User
from app.services.prices import get_quote, get_quotes_batch, get_history, get_fx_rate
from app.services.currency import normalize_currency
from app.services.portfolio_service import build_value_timeline

# ── Public portfolio view (no auth) ────────────────────────────

public_router = APIRouter(prefix="/api/public", tags=["public"])


@public_router.get("/portfolio/{token}")
async def get_public_portfolio(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()

    if not positions:
        return {
            "display_name": user.display_name,
            "total_value": 0, "total_cost": 0, "total_pnl": 0, "total_pnl_pct": 0,
            "cash_balance": 0, "positions_count": 0, "positions": [],
        }

    cash_pos = next((p for p in positions if p.symbol == "CASH"), None)
    stock_positions = [p for p in positions if p.symbol != "CASH"]

    if stock_positions:
        tickers = list({p.symbol for p in stock_positions})
        quotes = await get_quotes_batch(tickers)
        for p in stock_positions:
            q = quotes.get(p.symbol)
            if q:
                p.last_price = q["price"]

    BASE_CCY = "CHF"
    fx_rates: dict[str, float] = {}
    for ccy in {p.currency for p in stock_positions if p.currency != BASE_CCY}:
        fx_rates[ccy] = await get_fx_rate(ccy, BASE_CCY)

    def to_chf(amount: float, ccy: str) -> float:
        if ccy == BASE_CCY:
            return amount
        return amount * fx_rates.get(ccy, 1.0)

    total_value = sum(to_chf((p.last_price or p.avg_cost_price) * p.quantity, p.currency) for p in stock_positions)
    total_cost = sum(to_chf(p.avg_cost_price * p.quantity, p.currency) for p in stock_positions)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    cash_balance = cash_pos.quantity if cash_pos else 0

    sparklines: dict[str, list[float]] = {}
    for p in stock_positions:
        hist = await get_history(p.symbol, range="5d", interval="1d")
        if hist:
            sparklines[p.symbol] = [h["close"] for h in hist]

    # Trade history for first_bought / trade_count
    trade_dates: dict[str, dict] = {}
    trade_result = await db.execute(
        select(
            StockTransaction.symbol,
            func.min(StockTransaction.executed_at).label("first_buy"),
            func.count(StockTransaction.id).label("trade_count"),
        )
        .where(and_(StockTransaction.user_id == user.id, StockTransaction.type == "buy"))
        .group_by(StockTransaction.symbol)
    )
    for r in trade_result.all():
        trade_dates[r.symbol] = {"first_buy": r.first_buy.isoformat() if r.first_buy else None, "trades": r.trade_count}

    pos_list = []
    for p in stock_positions:
        q_data = quotes.get(p.symbol, {}) if stock_positions else {}
        mv_chf = to_chf((p.last_price or p.avg_cost_price) * p.quantity, p.currency)
        pnl_chf = to_chf((p.unrealized_pnl or 0), p.currency)
        td = trade_dates.get(p.symbol, {})
        pos_list.append({
            "id": p.id,
            "symbol": p.symbol,
            "name": q_data.get("name", p.name),
            "quantity": p.quantity,
            "avg_cost_price": p.avg_cost_price,
            "currency": p.currency,
            "last_price": p.last_price,
            "change": q_data.get("change", 0),
            "change_pct": q_data.get("change_pct", 0),
            "market_value": mv_chf,
            "unrealized_pnl": pnl_chf,
            "pnl_pct": ((p.last_price or p.avg_cost_price) / p.avg_cost_price - 1) * 100 if p.avg_cost_price else 0,
            "weight_pct": (mv_chf / total_value * 100) if total_value else 0,
            "first_bought": td.get("first_buy"),
            "trade_count": td.get("trades", 0),
            "earnings_date": p.earnings_date.isoformat() if p.earnings_date else None,
            "sparkline": sparklines.get(p.symbol, []),
        })

    return {
        "display_name": user.display_name,
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "cash_balance": cash_balance,
        "base_currency": BASE_CCY,
        "positions_count": len(pos_list),
        "positions": sorted(pos_list, key=lambda p: p["market_value"], reverse=True),
    }


@public_router.get("/portfolio/{token}/chart/{ticker}")
async def get_public_chart(token: str, ticker: str, range: str = "1y", interval: str | None = None, db: AsyncSession = Depends(get_db)):
    """Public price chart — validates the share token first."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Portfolio not found")
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
    """Public trade history — validates the share token first."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    query = select(StockTransaction).where(StockTransaction.user_id == user.id)
    if symbol:
        query = query.where(StockTransaction.symbol == symbol.upper())
    query = query.order_by(desc(StockTransaction.executed_at)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    currencies = {t.currency for t in trades if t.currency != "CHF"}
    fx: dict[str, float] = {}
    for ccy in currencies:
        fx[ccy] = await get_fx_rate(ccy, "CHF")

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
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

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
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return await build_value_timeline(db, user.id)


@public_router.get("/portfolio/{token}/history")
async def get_public_portfolio_history(token: str, days: int = 365, db: AsyncSession = Depends(get_db)):
    """Public portfolio value history."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(and_(PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.snapshot_date >= since))
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    return [{"date": s.snapshot_date.isoformat(), "value": s.total_value, "pnl": s.total_pnl} for s in result.scalars().all()]


