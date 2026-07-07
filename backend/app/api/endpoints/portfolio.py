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
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot
from app.models.user import User
from app.services.prices import get_quote, get_quotes_batch, get_history, get_fx_rate
from app.services.currency import normalize_currency

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
            "cash_balance": 0, "net_deposits": 0, "positions_count": 0, "positions": [],
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

    # Net deposits (all-time): CASH deposits minus withdrawals. This is the
    # denominator for true all-time P&L — market-value-of-stocks + cash minus
    # the money the user actually put in. Reading from cost-basis would
    # under-report P&L when realised gains have already been booked to cash.
    dep_result = await db.execute(
        select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(and_(
            StockTransaction.user_id == user.id,
            StockTransaction.symbol == "CASH",
            StockTransaction.type == "deposit",
        ))
    )
    wd_result = await db.execute(
        select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(and_(
            StockTransaction.user_id == user.id,
            StockTransaction.symbol == "CASH",
            StockTransaction.type == "withdraw",
        ))
    )
    net_deposits = float(dep_result.scalar() or 0) - float(wd_result.scalar() or 0)

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
            "earnings_date": p.earnings_date.isoformat() if p.earnings_date else None,
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
        "net_deposits": net_deposits,
        "base_currency": BASE_CCY,
        "fx_rates": {k: round(v, 4) for k, v in fx_rates.items()},
        "positions_count": len(pos_list),
        "positions": sorted(pos_list, key=lambda p: p["market_value"], reverse=True),
    }


# ── Trade (buy/sell/deposit/withdraw) ────────────────────────────

@router.post("/trade")
@router.post("/trades")
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

    # Auto-correct currency from yfinance (quote already returns normalized major currency)
    yf_ccy = quote.get("currency", "").upper()
    CASH_CCY = "CHF"
    trade_ccy = body.currency.upper() if body.currency else ""
    # Normalize user-supplied currency in case it's a subunit code
    trade_ccy, _ = normalize_currency(trade_ccy) if trade_ccy else ("", 1.0)
    if yf_ccy and trade_ccy != yf_ccy:
        logger.info(
            f"execute_trade: auto-correcting currency for {ticker}: "
            f"user-supplied '{body.currency}' -> yfinance '{yf_ccy}'"
        )
        trade_ccy = yf_ccy
    if trade_ccy != CASH_CCY:
        fx = await get_fx_rate(trade_ccy, CASH_CCY)
    else:
        fx = 1.0
    total_cost_chf = total_cost * fx

    # Get or create position
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user.id,
            StockPosition.symbol == ticker,
        ))
    )
    position = result.scalar_one_or_none()

    if trade_type == "buy":
        # Deduct from cash if enabled (cash is CHF-denominated, convert trade amount)
        if body.deduct_from_cash:
            cash = await _get_cash_position(db, user.id, account.id)
            if cash.quantity < total_cost_chf:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient cash: {cash.quantity:.2f} CHF, need {total_cost_chf:.2f} CHF. Deposit cash first or disable deduct_from_cash."
                )
            cash.quantity -= total_cost_chf

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
                currency=trade_ccy, last_price=quote["price"],
                last_price_at=datetime.now(timezone.utc),
            )
            db.add(position)

    elif trade_type == "sell":
        if not position or position.quantity < body.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient shares: {position.quantity if position else 0}")

        # Add proceeds to cash in CHF (convert from trade currency)
        if body.deduct_from_cash:
            proceeds_chf = ((price * body.quantity) - body.fees) * fx
            cash = await _get_cash_position(db, user.id, account.id)
            cash.quantity += proceeds_chf

        position.quantity -= body.quantity
        if position.quantity <= 0:
            await db.delete(position)

    # Log trade (use corrected trade_ccy, not raw body.currency)
    db.add(StockTransaction(
        user_id=user.id, account_id=account.id,
        symbol=ticker, type=trade_type,
        quantity=body.quantity, price=price,
        fees=body.fees, currency=trade_ccy,
        executed_at=trade_date,
    ))

    await db.commit()
    return {
        "status": "ok", "symbol": ticker, "type": trade_type,
        "quantity": body.quantity, "price": price,
        "currency": trade_ccy,
    }


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

    # Fetch FX rates for CHF conversion
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
async def get_price_chart(ticker: str, range: str = "1y", interval: str | None = None):
    valid_ranges = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}
    if range not in valid_ranges:
        raise HTTPException(status_code=400, detail=f"Invalid range")
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


# ── Portfolio value timeline (built from transactions + yfinance) ──

@router.get("/value-timeline")
async def get_value_timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build day-by-day portfolio value from actual transactions + historical prices."""
    return await _build_value_timeline(db, user.id)


async def _build_value_timeline(db: AsyncSession, user_id: str):
    """Shared logic for private + public value timeline."""
    # Get all trades ordered by date
    result = await db.execute(
        select(StockTransaction)
        .where(StockTransaction.user_id == user_id)
        .order_by(StockTransaction.executed_at)
    )
    all_trades = result.scalars().all()

    if not all_trades:
        return []

    # Collect unique stock symbols (exclude CASH)
    symbols = list({t.symbol for t in all_trades if t.symbol != "CASH"})

    # Fetch historical prices for each symbol from first trade date
    first_date = all_trades[0].executed_at.date()
    days_needed = (date.today() - first_date).days + 1
    if days_needed < 30:
        yf_range = "1mo"
    elif days_needed < 90:
        yf_range = "3mo"
    elif days_needed < 180:
        yf_range = "6mo"
    elif days_needed < 365:
        yf_range = "1y"
    elif days_needed < 730:
        yf_range = "2y"
    else:
        yf_range = "5y"

    # symbol -> {date_str -> close_price}
    price_history: dict[str, dict[str, float]] = {}
    # symbol -> currency (for FX conversion)
    symbol_currency: dict[str, str] = {}
    for sym in symbols:
        hist = await get_history(sym, range=yf_range, interval="1d")
        if hist:
            price_history[sym] = {h["date"]: h["close"] for h in hist}

    # Collect unique trade currencies and prefetch FX rates to CHF
    # (Cash position is always CHF-denominated; stock trades may be in any currency)
    trade_currencies: set[str] = {t.currency.upper() for t in all_trades if t.symbol != "CASH"}
    for t in all_trades:
        if t.symbol != "CASH":
            symbol_currency[t.symbol] = t.currency.upper()
    fx_rates: dict[str, float] = {}
    for ccy in trade_currencies:
        fx_rates[ccy] = await get_fx_rate(ccy, "CHF")

    def _to_chf(amount: float, ccy: str) -> float:
        return amount * fx_rates.get(ccy.upper(), 1.0)

    # Collect all unique dates from price history
    all_dates: set[str] = set()
    for prices in price_history.values():
        all_dates.update(prices.keys())
    # Also add trade dates
    for t in all_trades:
        all_dates.add(t.executed_at.date().isoformat())

    if not all_dates:
        return []

    sorted_dates = sorted(all_dates)

    # Walk through dates, building cumulative positions (all values in CHF)
    holdings: dict[str, float] = {}  # symbol -> quantity
    cash = 0.0  # CHF cash balance
    net_deposits = 0.0  # cumulative deposits minus withdrawals (CHF)
    trade_idx = 0

    timeline = []
    for d in sorted_dates:
        # Apply all trades on or before this date
        while trade_idx < len(all_trades):
            t = all_trades[trade_idx]
            td = t.executed_at.date().isoformat()
            if td > d:
                break

            if t.symbol == "CASH":
                # CASH deposits/withdrawals are already CHF-denominated
                if t.type == "deposit":
                    cash += t.quantity
                    net_deposits += t.quantity
                elif t.type == "withdraw":
                    cash -= t.quantity
                    net_deposits -= t.quantity
            elif t.type == "buy":
                trade_ccy = t.currency.upper()
                cost_chf = _to_chf(t.quantity * t.price + t.fees, trade_ccy)
                holdings[t.symbol] = holdings.get(t.symbol, 0) + t.quantity
                cash -= cost_chf
            elif t.type == "sell":
                trade_ccy = t.currency.upper()
                proceeds_chf = _to_chf(t.quantity * t.price - t.fees, trade_ccy)
                holdings[t.symbol] = max(0, holdings.get(t.symbol, 0) - t.quantity)
                cash += proceeds_chf

            trade_idx += 1

        # Calculate portfolio value on this date (all in CHF)
        total_value = cash
        for sym, qty in holdings.items():
            if qty <= 0:
                continue
            # Find price on this date (or most recent before)
            prices = price_history.get(sym, {})
            price = prices.get(d)
            if price is None:
                # Find the most recent price before this date
                prev_dates = [pd for pd in sorted(prices.keys()) if pd <= d]
                price = prices[prev_dates[-1]] if prev_dates else 0
            # Historical price is in stock's native currency; convert to CHF using current FX rate
            # (Using current FX rate as a simplification — historical FX rates are out of scope)
            sym_ccy = symbol_currency.get(sym, "USD")
            total_value += _to_chf(qty * price, sym_ccy)

        # Find trades on this date for markers
        day_trades = [
            {"symbol": t.symbol, "type": t.type, "quantity": t.quantity, "price": t.price}
            for t in all_trades
            if t.executed_at.date().isoformat() == d
        ]

        timeline.append({
            "date": d,
            "value": round(total_value, 2),
            "cost": round(net_deposits, 2),
            "pnl": round(total_value - net_deposits, 2),
            "trades": day_trades if day_trades else None,
        })

    return timeline


class ClassifyRequest(BaseModel):
    asset_type: str  # equity|etf|index|crypto|bond|commodity|cash


@router.get("/classifications")
async def list_classifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every per-symbol classification this user has (or that was auto-detected)."""
    from app.models.stock import SymbolClassification
    result = await db.execute(
        select(SymbolClassification).where(SymbolClassification.user_id == user.id)
    )
    rows = result.scalars().all()
    return [
        {"symbol": r.symbol, "asset_type": r.asset_type, "source": r.source,
         "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]


@router.post("/classifications/{symbol}")
async def set_classification(
    symbol: str,
    body: ClassifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User sets/overrides a symbol's asset_type. Auto-classifier won't overwrite this."""
    from app.services import classification as classification_svc
    try:
        row = await classification_svc.set_classification(
            db, user.id, symbol, body.asset_type, source="user"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"symbol": row.symbol, "asset_type": row.asset_type, "source": row.source}


@router.post("/classifications/backfill")
async def backfill_classifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Classify every symbol the user has touched that isn't already classified."""
    from app.services import classification as classification_svc
    return await classification_svc.backfill_user_classifications(db, user.id)


# ── Live prices (lightweight, polled every few seconds for live ticker) ──

@router.get("/live-prices")
async def get_live_prices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight live prices for held positions.

    Routing: symbols that sit on a Saxo-sourced account are priced via Saxo's
    native infoprices endpoint; everything else falls back to yfinance. If
    Saxo pricing fails we silently fall back per-symbol so the ticker keeps
    working during Saxo outages.
    """
    from app.brokers.saxo import sync as saxo_sync
    from app.brokers import get_adapter

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

    # Which accounts are Saxo-sourced?
    saxo_account_ids: set[str] = set()
    acct_result = await db.execute(
        select(Account).where(and_(
            Account.user_id == user.id,
            Account.name.like(f"{saxo_sync.SAXO_ACCOUNT_NAME_PREFIX}%"),
        ))
    )
    for a in acct_result.scalars().all():
        saxo_account_ids.add(a.id)

    saxo_symbols = {p.symbol for p in positions if p.account_id in saxo_account_ids}
    other_symbols = {p.symbol for p in positions if p.account_id not in saxo_account_ids}

    quotes: dict[str, dict] = {}

    if saxo_symbols:
        try:
            saxo_adapter = get_adapter("saxo")
            saxo_quotes = await saxo_adapter.get_live_prices(
                db, user.id, symbols=list(saxo_symbols)
            )
            for sym, q in saxo_quotes.items():
                quotes[sym] = q
            # Fall back to yfinance for symbols Saxo couldn't price.
            missing_from_saxo = saxo_symbols - set(saxo_quotes.keys())
            other_symbols |= missing_from_saxo
        except Exception:
            # Broker-side failure — fall back to yfinance for all symbols.
            other_symbols |= saxo_symbols

    if other_symbols:
        yf_quotes = await get_quotes_batch(list(other_symbols), cache_ttl=15)
        for sym, q in yf_quotes.items():
            if sym not in quotes:
                quotes[sym] = {
                    "price": q["price"],
                    "change": q.get("change", 0),
                    "change_pct": q.get("change_pct", 0),
                    "source": "yfinance",
                }

    # Strip source from payload for backwards compat (frontend doesn't need it yet).
    return {
        sym: {"price": q["price"], "change": q.get("change", 0), "change_pct": q.get("change_pct", 0)}
        for sym, q in quotes.items()
    }


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
