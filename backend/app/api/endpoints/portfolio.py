"""Portfolio endpoints — positions, trades, cash, live prices, charts."""
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot, MarketAnalysis
from app.models.user import User
from app.services.prices import get_quote, get_quotes_batch, get_history, get_fx_rate

router = APIRouter(prefix="/api/dashboard/portfolio", tags=["portfolio"])


# ── Schemas ──────────────────────────────────────────────────────

class TradeRequest(BaseModel):
    symbol: str
    type: str = "buy"  # buy | sell | deposit | withdraw
    quantity: float
    price: float = 0  # price per share (0 for cash deposit/withdraw)
    currency: str = "USD"
    date: str | None = None  # ISO date, defaults to today
    fees: float = 0
    deduct_from_cash: bool = True  # Automatically adjust cash balance


class UpdatePosition(BaseModel):
    quantity: float | None = None
    avg_cost_price: float | None = None


# ── Helpers ──────────────────────────────────────────────────────

async def _get_or_create_brokerage(db: AsyncSession, user_id: str) -> Account:
    result = await db.execute(
        select(Account).where(and_(Account.user_id == user_id, Account.type == "brokerage"))
    )
    account = result.scalar_one_or_none()
    if not account:
        account = Account(user_id=user_id, name="Portfolio", type="brokerage", currency="USD")
        db.add(account)
        await db.flush()
    return account


async def _get_cash_position(db: AsyncSession, user_id: str, account_id: str) -> StockPosition:
    """Get or create the CASH position."""
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user_id,
            StockPosition.symbol == "CASH",
        ))
    )
    cash = result.scalar_one_or_none()
    if not cash:
        cash = StockPosition(
            user_id=user_id, account_id=account_id,
            symbol="CASH", name="Cash (Uninvested)",
            quantity=0, avg_cost_price=1, currency="CHF",
        )
        db.add(cash)
        await db.flush()
    return cash


# ── Portfolio overview with live prices ──────────────────────────

@router.get("")
async def get_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()

    if not positions:
        return {
            "total_value": 0, "total_cost": 0, "total_pnl": 0, "total_pnl_pct": 0,
            "cash_balance": 0, "positions_count": 0, "positions": [],
        }

    # Separate cash from stock positions
    cash_pos = next((p for p in positions if p.symbol == "CASH"), None)
    stock_positions = [p for p in positions if p.symbol != "CASH"]

    # Fetch live prices for stocks
    if stock_positions:
        tickers = list({p.symbol for p in stock_positions})
        quotes = await get_quotes_batch(tickers)

        for p in stock_positions:
            q = quotes.get(p.symbol)
            if q:
                p.last_price = q["price"]
                p.last_price_at = datetime.now(timezone.utc)
                p.unrealized_pnl = (q["price"] - p.avg_cost_price) * p.quantity
        await db.commit()

    # Fetch FX rates to convert everything to CHF
    BASE_CCY = "CHF"
    fx_rates: dict[str, float] = {}
    currencies_needed = {p.currency for p in stock_positions if p.currency != BASE_CCY}
    for ccy in currencies_needed:
        fx_rates[ccy] = await get_fx_rate(ccy, BASE_CCY)

    def to_chf(amount: float, ccy: str) -> float:
        if ccy == BASE_CCY:
            return amount
        return amount * fx_rates.get(ccy, 1.0)

    total_value = sum(to_chf((p.last_price or p.avg_cost_price) * p.quantity, p.currency) for p in stock_positions)
    total_cost = sum(to_chf(p.avg_cost_price * p.quantity, p.currency) for p in stock_positions)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    cash_balance = cash_pos.quantity if cash_pos else 0  # Already in CHF

    # Get trade history for "bought on" dates
    trade_dates = {}
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

    # Fetch 7-day sparkline data for each stock
    sparklines: dict[str, list[float]] = {}
    if stock_positions:
        for p in stock_positions:
            hist = await get_history(p.symbol, range="5d", interval="1d")
            if hist:
                sparklines[p.symbol] = [h["close"] for h in hist]

    pos_list = []
    for p in stock_positions:
        q_data = quotes.get(p.symbol, {}) if stock_positions else {}
        mv_local = (p.last_price or p.avg_cost_price) * p.quantity
        mv_chf = to_chf(mv_local, p.currency)
        pnl_local = (p.unrealized_pnl or 0)
        pnl_chf = to_chf(pnl_local, p.currency)
        fx = fx_rates.get(p.currency, 1.0)
        td = trade_dates.get(p.symbol, {})
        pos_list.append({
            "id": p.id,
            "symbol": p.symbol,
            "name": q_data.get("name", p.name),
            "quantity": p.quantity,
            "avg_cost_price": p.avg_cost_price,
            "currency": p.currency,
            "fx_rate": fx if p.currency != BASE_CCY else None,
            "last_price": p.last_price,
            "change": q_data.get("change", 0),
            "change_pct": q_data.get("change_pct", 0),
            "market_value": mv_chf,
            "unrealized_pnl": pnl_chf,
            "pnl_pct": ((p.last_price or p.avg_cost_price) / p.avg_cost_price - 1) * 100 if p.avg_cost_price else 0,
            "weight_pct": (mv_chf / total_value * 100) if total_value else 0,
            "first_bought": td.get("first_buy"),
            "trade_count": td.get("trades", 0),
            "sparkline": sparklines.get(p.symbol, []),
        })

    # Save daily snapshot
    today = date.today()
    snap_result = await db.execute(
        select(PortfolioSnapshot).where(and_(
            PortfolioSnapshot.user_id == user.id,
            PortfolioSnapshot.snapshot_date == today,
        ))
    )
    snap = snap_result.scalar_one_or_none()
    if snap:
        snap.total_value = total_value + cash_balance
        snap.total_cost = total_cost
        snap.total_pnl = total_pnl
    else:
        db.add(PortfolioSnapshot(
            user_id=user.id, total_value=total_value + cash_balance,
            total_cost=total_cost, total_pnl=total_pnl,
            snapshot_date=today,
        ))
    await db.commit()

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "cash_balance": cash_balance,
        "base_currency": BASE_CCY,
        "fx_rates": {k: round(v, 4) for k, v in fx_rates.items()},
        "positions_count": len(pos_list),
        "positions": sorted(pos_list, key=lambda p: p["market_value"], reverse=True),
    }


# ── Trade (buy/sell/deposit/withdraw) ────────────────────────────

@router.post("/trade")
async def execute_trade(
    body: TradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a trade. Supports buy, sell, deposit (cash), withdraw (cash)."""
    account = await _get_or_create_brokerage(db, user.id)
    ticker = body.symbol.upper().strip()
    trade_type = body.type.lower()
    trade_date = datetime.fromisoformat(body.date).replace(tzinfo=timezone.utc) if body.date else datetime.now(timezone.utc)

    if trade_type not in ("buy", "sell", "deposit", "withdraw"):
        raise HTTPException(status_code=400, detail="Type must be buy, sell, deposit, or withdraw")

    # Handle cash deposit/withdraw
    if trade_type in ("deposit", "withdraw"):
        cash = await _get_cash_position(db, user.id, account.id)
        if trade_type == "deposit":
            cash.quantity += body.quantity
        else:
            if cash.quantity < body.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient cash: {cash.quantity:.2f}")
            cash.quantity -= body.quantity

        db.add(StockTransaction(
            user_id=user.id, account_id=account.id,
            symbol="CASH", type=trade_type,
            quantity=body.quantity, price=1,
            fees=0, currency=body.currency,
            executed_at=trade_date,
        ))
        await db.commit()
        return {"status": "ok", "cash_balance": cash.quantity}

    # Validate ticker
    if ticker == "CASH":
        raise HTTPException(status_code=400, detail="Use deposit/withdraw for cash")

    quote = await get_quote(ticker)
    if not quote:
        raise HTTPException(status_code=400, detail=f"Ticker {ticker} not found")

    price = body.price or quote["price"]
    total_cost = price * body.quantity + body.fees

    # Get or create position
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user.id,
            StockPosition.symbol == ticker,
        ))
    )
    position = result.scalar_one_or_none()

    if trade_type == "buy":
        # Deduct from cash if enabled
        if body.deduct_from_cash:
            cash = await _get_cash_position(db, user.id, account.id)
            if cash.quantity < total_cost:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient cash: {cash.quantity:.2f} CHF, need {total_cost:.2f}. Deposit cash first or disable deduct_from_cash."
                )
            cash.quantity -= total_cost

        if position:
            # Update avg cost: weighted average
            old_total = position.avg_cost_price * position.quantity
            new_total = price * body.quantity
            position.quantity += body.quantity
            position.avg_cost_price = (old_total + new_total) / position.quantity if position.quantity else 0
        else:
            position = StockPosition(
                user_id=user.id, account_id=account.id,
                symbol=ticker, name=quote.get("name", ticker),
                quantity=body.quantity, avg_cost_price=price,
                currency=body.currency, last_price=quote["price"],
                last_price_at=datetime.now(timezone.utc),
            )
            db.add(position)

    elif trade_type == "sell":
        if not position or position.quantity < body.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient shares: {position.quantity if position else 0}")

        # Add proceeds to cash
        if body.deduct_from_cash:
            cash = await _get_cash_position(db, user.id, account.id)
            cash.quantity += (price * body.quantity) - body.fees

        position.quantity -= body.quantity
        if position.quantity <= 0:
            await db.delete(position)

    # Log trade
    db.add(StockTransaction(
        user_id=user.id, account_id=account.id,
        symbol=ticker, type=trade_type,
        quantity=body.quantity, price=price,
        fees=body.fees, currency=body.currency,
        executed_at=trade_date,
    ))

    await db.commit()
    return {"status": "ok", "symbol": ticker, "type": trade_type, "quantity": body.quantity, "price": price}


# ── Trade history ────────────────────────────────────────────────

@router.get("/trades")
async def get_trades(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(StockTransaction).where(StockTransaction.user_id == user.id)
    if symbol:
        query = query.where(StockTransaction.symbol == symbol.upper())
    query = query.order_by(desc(StockTransaction.executed_at)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()
    return [
        {
            "id": t.id, "symbol": t.symbol, "type": t.type,
            "quantity": t.quantity, "price": t.price, "fees": t.fees,
            "currency": t.currency, "date": t.executed_at.isoformat(),
            "total": t.quantity * t.price + (t.fees if t.type == "buy" else -t.fees),
        }
        for t in trades
    ]


# ── CRUD (direct edit, no trade log) ────────────────────────────

@router.patch("/{position_id}")
async def update_position(
    position_id: str,
    body: UpdatePosition,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.id == position_id, StockPosition.user_id == user.id,
        ))
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    if body.quantity is not None:
        pos.quantity = body.quantity
    if body.avg_cost_price is not None:
        pos.avg_cost_price = body.avg_cost_price
    await db.commit()
    return {"status": "ok"}


@router.delete("/{position_id}")
async def delete_position(
    position_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.id == position_id, StockPosition.user_id == user.id,
        ))
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    await db.delete(pos)
    await db.commit()
    return {"status": "ok"}


# ── Price chart ──────────────────────────────────────────────────

@router.get("/chart/{ticker}")
async def get_price_chart(ticker: str, range: str = "1y", interval: str = "1d"):
    valid_ranges = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}
    if range not in valid_ranges:
        raise HTTPException(status_code=400, detail=f"Invalid range")
    data = await get_history(ticker, range=range, interval=interval)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return {"ticker": ticker, "range": range, "data": data}


# ── Portfolio history ────────────────────────────────────────────

@router.get("/history")
async def get_portfolio_history(
    days: int = 90,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(and_(PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.snapshot_date >= since))
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    return [{"date": s.snapshot_date.isoformat(), "value": s.total_value, "pnl": s.total_pnl} for s in result.scalars().all()]


# ── Per-stock analyses ──────────────────────────────────────────

@router.get("/analyses/by-stock")
async def get_analyses_by_stock(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest analysis for each stock symbol."""
    result = await db.execute(
        select(MarketAnalysis).where(and_(MarketAnalysis.user_id == user.id, MarketAnalysis.analysis_type == "portfolio"))
        .order_by(desc(MarketAnalysis.created_at))
    )
    stock_analyses: dict[str, dict] = {}
    for a in result.scalars().all():
        for s in a.content.get("stocks", []):
            sym = s.get("symbol")
            if sym and sym not in stock_analyses:
                stock_analyses[sym] = {
                    "analysis_id": a.id,
                    "stock": s,
                    "market_summary": a.content.get("market_summary", ""),
                    "market_sentiment": a.content.get("market_sentiment", ""),
                    "created_at": a.created_at.isoformat(),
                }
    return stock_analyses


@router.get("/analyses/{symbol}")
async def get_stock_analyses(
    symbol: str,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get older analyses for a specific stock."""
    result = await db.execute(
        select(MarketAnalysis).where(and_(MarketAnalysis.user_id == user.id, MarketAnalysis.analysis_type == "portfolio"))
        .order_by(desc(MarketAnalysis.created_at)).limit(limit)
    )
    out = []
    for a in result.scalars().all():
        for s in a.content.get("stocks", []):
            if s.get("symbol") == symbol.upper():
                out.append({
                    "id": a.id,
                    "stock": s,
                    "market_summary": a.content.get("market_summary", ""),
                    "market_sentiment": a.content.get("market_sentiment", ""),
                    "created_at": a.created_at.isoformat(),
                })
    return out


# ── Public sharing ──────────────────────────────────────────────

@router.get("/public/status")
async def get_public_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"enabled": user.public_portfolio, "token": user.public_share_token}


@router.post("/public/toggle")
async def toggle_public_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.public_portfolio:
        # Turning off — clear the token so old links stop working
        user.public_portfolio = False
        user.public_share_token = None
    else:
        # Turning on — generate a fresh token
        user.public_portfolio = True
        user.public_share_token = secrets.token_urlsafe(32)
    await db.commit()
    return {"enabled": user.public_portfolio, "token": user.public_share_token}


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

    pos_list = []
    for p in stock_positions:
        q_data = quotes.get(p.symbol, {}) if stock_positions else {}
        mv_chf = to_chf((p.last_price or p.avg_cost_price) * p.quantity, p.currency)
        pnl_chf = to_chf((p.unrealized_pnl or 0), p.currency)
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

    stock_analyses: dict[str, dict] = {}
    for a in all_analyses:
        stocks = a.content.get("stocks", [])
        for s in stocks:
            sym = s.get("symbol")
            if sym and sym not in stock_analyses:
                stock_analyses[sym] = {
                    "analysis_id": a.id,
                    "stock": s,
                    "market_summary": a.content.get("market_summary", ""),
                    "market_sentiment": a.content.get("market_sentiment", ""),
                    "created_at": a.created_at.isoformat(),
                }

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
        "stock_analyses": stock_analyses,
        "economy_analysis": _fmt_analysis(ea_result.scalar_one_or_none()),
    }


@public_router.get("/portfolio/{token}/chart/{ticker}")
async def get_public_chart(token: str, ticker: str, range: str = "1y", interval: str = "1d", db: AsyncSession = Depends(get_db)):
    """Public price chart — validates the share token first."""
    result = await db.execute(
        select(User).where(and_(User.public_share_token == token, User.public_portfolio == True))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Portfolio not found")
    valid_ranges = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}
    if range not in valid_ranges:
        raise HTTPException(status_code=400, detail="Invalid range")
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
    return [
        {
            "id": t.id, "symbol": t.symbol, "type": t.type,
            "quantity": t.quantity, "price": t.price, "fees": t.fees,
            "currency": t.currency, "date": t.executed_at.isoformat(),
            "total": t.quantity * t.price + (t.fees if t.type == "buy" else -t.fees),
        }
        for t in trades
    ]


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
                    "id": a.id,
                    "stock": s,
                    "market_summary": a.content.get("market_summary", ""),
                    "market_sentiment": a.content.get("market_sentiment", ""),
                    "created_at": a.created_at.isoformat(),
                })
    return out
