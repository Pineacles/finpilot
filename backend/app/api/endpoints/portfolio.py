"""Portfolio endpoints — positions, trades, cash, live prices, charts."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot
from app.models.user import User
from app.services.prices import get_quote, get_quotes_batch, get_history

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

    total_value = sum((p.last_price or p.avg_cost_price) * p.quantity for p in stock_positions)
    total_cost = sum(p.avg_cost_price * p.quantity for p in stock_positions)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    cash_balance = cash_pos.quantity if cash_pos else 0

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
        mv = (p.last_price or p.avg_cost_price) * p.quantity
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
            "market_value": mv,
            "unrealized_pnl": p.unrealized_pnl or 0,
            "pnl_pct": ((p.last_price or p.avg_cost_price) / p.avg_cost_price - 1) * 100 if p.avg_cost_price else 0,
            "weight_pct": (mv / total_value * 100) if total_value else 0,
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
