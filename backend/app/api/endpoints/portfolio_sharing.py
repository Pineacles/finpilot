"""Public portfolio sharing endpoints — unauthenticated read-only views."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot, MarketAnalysis, PostMortem, BuyAssessment
from app.models.user import User
from app.services.prices import get_quote, get_quotes_batch, get_history, get_fx_rate
from app.services.currency import normalize_currency

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

    # Fetch latest analysis per stock symbol
    def _fmt_analysis(a):
        if not a:
            return None
        return {"id": a.id, "analysis_type": a.analysis_type, "content": a.content, "created_at": a.created_at.isoformat()}

    # Get ALL portfolio analyses, then pick the latest per symbol
    all_pa_result = await db.execute(
        select(MarketAnalysis).where(and_(MarketAnalysis.user_id == user.id, MarketAnalysis.analysis_type == "portfolio"))
        .order_by(desc(MarketAnalysis.created_at))
    )
    all_analyses = all_pa_result.scalars().all()

    held_symbols = {p.symbol for p in stock_positions if p.quantity > 0}
    current_analyses: dict[str, dict] = {}
    past_analyses: dict[str, dict] = {}
    for a in all_analyses:
        stocks = a.content.get("stocks", [])
        for s in stocks:
            sym = s.get("symbol")
            if not sym:
                continue
            entry = {
                "analysis_id": a.id,
                "stock": s,
                "market_summary": a.content.get("market_summary", ""),
                "market_sentiment": a.content.get("market_sentiment", ""),
                "created_at": a.created_at.isoformat(),
            }
            if sym in held_symbols:
                if sym not in current_analyses:
                    current_analyses[sym] = entry
            else:
                if sym not in past_analyses:
                    past_analyses[sym] = entry

    ea_result = await db.execute(
        select(MarketAnalysis).where(and_(MarketAnalysis.user_id == user.id, MarketAnalysis.analysis_type == "economy"))
        .order_by(desc(MarketAnalysis.created_at)).limit(1)
    )

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
        "stock_analyses": current_analyses,
        "past_stock_analyses": past_analyses,
        "economy_analysis": _fmt_analysis(ea_result.scalar_one_or_none()),
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


@public_router.get("/portfolio/{token}/economy-history")
async def get_public_economy_history(token: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Public economy analysis history."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    result = await db.execute(
        select(MarketAnalysis).where(and_(MarketAnalysis.user_id == user.id, MarketAnalysis.analysis_type == "economy"))
        .order_by(desc(MarketAnalysis.created_at)).limit(limit)
    )
    return [
        {"id": a.id, "analysis_type": a.analysis_type, "content": a.content, "created_at": a.created_at.isoformat()}
        for a in result.scalars().all()
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
    return await _build_value_timeline(db, user.id)


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


@public_router.get("/portfolio/{token}/analyses/{symbol}")
async def get_public_stock_analyses(token: str, symbol: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Get older analyses for a specific stock."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    result = await db.execute(
        select(MarketAnalysis).where(and_(MarketAnalysis.user_id == user.id, MarketAnalysis.analysis_type == "portfolio"))
        .order_by(desc(MarketAnalysis.created_at)).limit(limit)
    )
    out = []
    for a in result.scalars().all():
        for s in a.content.get("stocks", []):
            if s.get("symbol") == symbol.upper():
                out.append({
                    "analysis_id": a.id,
                    "stock": s,
                    "market_summary": a.content.get("market_summary", ""),
                    "market_sentiment": a.content.get("market_sentiment", ""),
                    "created_at": a.created_at.isoformat(),
                })
    return out


@public_router.get("/portfolio/{token}/journal")
async def get_public_journal(token: str, db: AsyncSession = Depends(get_db)):
    """Public read-only journal — post-mortems and buy assessments for a shared portfolio."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    pm_result = await db.execute(
        select(PostMortem).where(PostMortem.user_id == user.id)
        .order_by(desc(PostMortem.created_at)).limit(50)
    )
    post_mortems = [
        {
            "id": pm.id,
            "symbol": pm.symbol,
            "entry_price": pm.entry_price,
            "exit_price": pm.exit_price,
            "pnl_pct": pm.pnl_pct,
            "notes": pm.notes,
            "created_at": pm.created_at.isoformat(),
        }
        for pm in pm_result.scalars().all()
    ]

    ba_result = await db.execute(
        select(BuyAssessment).where(BuyAssessment.user_id == user.id)
        .order_by(desc(BuyAssessment.created_at)).limit(50)
    )
    buy_assessments = [
        {
            "id": ba.id,
            "symbol": ba.symbol,
            "recommendation": ba.recommendation,
            "target_price": ba.target_price,
            "stop_loss": ba.stop_loss,
            "thesis": ba.thesis,
            "risk_factors": ba.risk_factors,
            "conviction": ba.conviction,
            "time_horizon": ba.time_horizon,
            "assessed_at": ba.assessed_at.isoformat(),
            "created_at": ba.created_at.isoformat(),
        }
        for ba in ba_result.scalars().all()
    ]

    return {"post_mortems": post_mortems, "buy_assessments": buy_assessments}
