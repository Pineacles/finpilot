"""Business logic for stock portfolio positions, trades, and valuation.

Shared between the JWT-authenticated dashboard router (portfolio.py), the
API-key agent router (agent_portfolio_router.py), and the unauthenticated
public-share router (portfolio_sharing.py) so the three surfaces can't drift
out of sync. Routers stay thin: parse/validate the request, call into this
module, shape the response.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot, SymbolClassification
from app.services.prices import get_quote, get_quotes_batch, get_history, get_fx_rate, get_cached_fx_rate
from app.services.currency import normalize_currency

logger = logging.getLogger(__name__)

BASE_CCY = "CHF"

# A position is flagged `price_stale` when its live quote fetch failed *this
# request* AND the last successfully-fetched price is older than this.
STALE_PRICE_THRESHOLD = timedelta(minutes=15)


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    """Some DB drivers (e.g. SQLite, some asyncpg/timezone setups) hand back
    naive datetimes for a DateTime(timezone=True) column even though we
    always write UTC-aware values. Normalize before comparing against
    datetime.now(timezone.utc) — otherwise a naive/aware subtraction raises
    TypeError and would take down the whole portfolio response."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

# Best-effort hint for "you probably meant the listing on this exchange"
# when a trade's user-supplied currency doesn't match the ticker's quote
# currency. Not exhaustive — just a nudge, shown alongside the raw mismatch.
TICKER_SUFFIX_HINTS: dict[str, str] = {
    "GBP": ".L",   # London Stock Exchange
    "EUR": ".DE",  # Frankfurt (common default; actual exchange varies)
    "CHF": ".SW",  # SIX Swiss Exchange
    "CAD": ".TO",  # Toronto
    "AUD": ".AX",  # ASX
    "HKD": ".HK",  # Hong Kong
    "JPY": ".T",   # Tokyo
    "SEK": ".ST",  # Stockholm
    "NOK": ".OL",  # Oslo
    "DKK": ".CO",  # Copenhagen
    "SGD": ".SI",  # Singapore
    "KRW": ".KS",  # Korea
}


def suggest_ticker_suffix(ticker: str, quote_currency: str) -> str | None:
    """Best-effort 'you probably meant TICKER.XX' suggestion for a currency
    mismatch. Returns None if we don't have a hint or the ticker already
    carries that suffix."""
    suffix = TICKER_SUFFIX_HINTS.get(quote_currency.upper())
    if not suffix or ticker.upper().endswith(suffix):
        return None
    return f"{ticker}{suffix}"


class PositionNotFoundError(Exception):
    def __init__(self, position_id: str):
        self.position_id = position_id
        super().__init__(f"Position not found: {position_id}")


class TradeNotFoundError(Exception):
    def __init__(self, trade_id: str):
        self.trade_id = trade_id
        super().__init__(f"Trade not found: {trade_id}")


class InsufficientCashError(Exception):
    def __init__(self, available: float, needed: float | None = None):
        self.available = available
        self.needed = needed
        super().__init__("Insufficient cash")


class InsufficientSharesError(Exception):
    def __init__(self, available: float):
        self.available = available
        super().__init__("Insufficient shares")


class InvalidTickerError(Exception):
    def __init__(self, ticker: str):
        self.ticker = ticker
        super().__init__(f"Ticker not found: {ticker}")


class CurrencyMismatchError(Exception):
    """Raised by execute_trade when the user-supplied currency doesn't match
    the ticker's live quote currency and the caller hasn't confirmed the
    override. We never silently overwrite the user's input."""
    def __init__(self, ticker: str, user_currency: str, quote_currency: str):
        self.ticker = ticker
        self.user_currency = user_currency
        self.quote_currency = quote_currency
        super().__init__(
            f"Currency mismatch for {ticker}: entered {user_currency}, "
            f"quote is in {quote_currency}"
        )


class FxRateUnavailableError(Exception):
    def __init__(self, from_ccy: str, to_ccy: str):
        self.from_ccy = from_ccy
        self.to_ccy = to_ccy
        super().__init__(f"Exchange rate unavailable for {from_ccy}->{to_ccy}")


# ── Helpers ──────────────────────────────────────────────────────

async def get_or_create_brokerage(db: AsyncSession, user_id: str) -> Account:
    result = await db.execute(
        select(Account).where(and_(Account.user_id == user_id, Account.type == "brokerage"))
    )
    account = result.scalar_one_or_none()
    if not account:
        account = Account(user_id=user_id, name="Portfolio", type="brokerage", currency="USD")
        db.add(account)
        await db.flush()
    return account


async def get_cash_position(db: AsyncSession, user_id: str, account_id: str) -> StockPosition:
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

async def _classification_map(db: AsyncSession, user_id: str, symbols: set[str]) -> dict[str, str]:
    if not symbols:
        return {}
    result = await db.execute(
        select(SymbolClassification).where(and_(
            SymbolClassification.user_id == user_id,
            SymbolClassification.symbol.in_(symbols),
        ))
    )
    return {r.symbol: r.asset_type for r in result.scalars().all()}


async def _price_stock_positions(
    db: AsyncSession, stock_positions: list[StockPosition]
) -> tuple[dict[str, dict], set[str], list[str]]:
    """Refresh live quotes onto `stock_positions` (persists last_price /
    last_price_at / unrealized_pnl for successful fetches only — a failed
    fetch this request never bumps last_price_at, so staleness stays honest).

    Returns (quotes, failed_symbols, warnings).
    """
    quotes: dict[str, dict] = {}
    failed_symbols: set[str] = set()
    warnings: list[str] = []

    if stock_positions:
        tickers = list({p.symbol for p in stock_positions})
        quotes = await get_quotes_batch(tickers)

        now = datetime.now(timezone.utc)
        for p in stock_positions:
            q = quotes.get(p.symbol)
            if q:
                p.last_price = q["price"]
                if not q.get("quote_fetch_failed"):
                    p.last_price_at = now
                else:
                    failed_symbols.add(p.symbol)
                p.unrealized_pnl = (q["price"] - p.avg_cost_price) * p.quantity
            else:
                failed_symbols.add(p.symbol)
        await db.commit()

    if failed_symbols:
        warnings.append(
            f"Live price refresh failed for {', '.join(sorted(failed_symbols))} — "
            f"showing the last known price instead."
        )

    return quotes, failed_symbols, warnings


async def _fx_rates_for_positions(
    stock_positions: list[StockPosition],
) -> tuple[dict[str, float], set[str], list[str]]:
    """Resolve CHF FX rates for every currency in use. Never silently
    defaults a missing rate to 1.0: falls back to the last known cached
    rate (with a warning), or — if we've never known this rate — excludes
    that currency's positions from CHF totals (with a warning naming them).

    Returns (fx_rates, currencies_excluded_from_totals, warnings).
    """
    fx_rates: dict[str, float] = {}
    excluded_currencies: set[str] = set()
    warnings: list[str] = []

    currencies_needed = {p.currency for p in stock_positions if p.currency != BASE_CCY}
    for ccy in currencies_needed:
        rate = await get_fx_rate(ccy, BASE_CCY)
        if rate is not None:
            fx_rates[ccy] = rate
            continue

        stale_rate = get_cached_fx_rate(ccy, BASE_CCY)
        if stale_rate is not None:
            fx_rates[ccy] = stale_rate
            warnings.append(
                f"Live {ccy}→{BASE_CCY} exchange rate lookup failed — using the last known rate."
            )
        else:
            excluded_currencies.add(ccy)
            affected = sorted({p.symbol for p in stock_positions if p.currency == ccy})
            warnings.append(
                f"No {ccy}→{BASE_CCY} exchange rate available — "
                f"{', '.join(affected)} excluded from CHF totals until it's back."
            )

    return fx_rates, excluded_currencies, warnings


async def _build_holdings_payload(db: AsyncSession, user_id: str, positions: list[StockPosition]) -> dict:
    """Shared valuation core for the private dashboard and the public share
    view: live prices, CHF conversion, staleness, asset-type, warnings.
    Does NOT persist a snapshot or compute net_deposits — callers that need
    those (the private view) add them on top.
    """
    cash_pos = next((p for p in positions if p.symbol == "CASH"), None)
    stock_positions = [p for p in positions if p.symbol != "CASH"]
    cash_balance = cash_pos.quantity if cash_pos else 0  # Already in CHF

    if not stock_positions:
        return {
            "total_value": 0, "total_cost": 0, "total_pnl": 0, "total_pnl_pct": 0,
            "cash_balance": cash_balance, "fx_rates": {}, "positions": [], "warnings": [],
        }

    quotes, failed_symbols, price_warnings = await _price_stock_positions(db, stock_positions)
    fx_rates, excluded_currencies, fx_warnings = await _fx_rates_for_positions(stock_positions)
    warnings = [*price_warnings, *fx_warnings]

    def to_chf(amount: float, ccy: str) -> float | None:
        if ccy == BASE_CCY:
            return amount
        if ccy in excluded_currencies:
            return None
        return amount * fx_rates.get(ccy, 1.0)

    valued = []
    for p in stock_positions:
        mv = to_chf((p.last_price or p.avg_cost_price) * p.quantity, p.currency)
        cost = to_chf(p.avg_cost_price * p.quantity, p.currency)
        valued.append((p, mv, cost))

    total_value = sum(mv for _, mv, _ in valued if mv is not None)
    total_cost = sum(cost for _, _, cost in valued if cost is not None)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    # Trade history for "bought on" dates
    trade_dates: dict[str, dict] = {}
    trade_result = await db.execute(
        select(
            StockTransaction.symbol,
            func.min(StockTransaction.executed_at).label("first_buy"),
            func.count(StockTransaction.id).label("trade_count"),
        )
        .where(and_(StockTransaction.user_id == user_id, StockTransaction.type == "buy"))
        .group_by(StockTransaction.symbol)
    )
    for r in trade_result.all():
        trade_dates[r.symbol] = {"first_buy": r.first_buy.isoformat() if r.first_buy else None, "trades": r.trade_count}

    # 7-day sparkline data for each stock
    sparklines: dict[str, list[float]] = {}
    for p in stock_positions:
        hist = await get_history(p.symbol, range="5d", interval="1d")
        if hist:
            sparklines[p.symbol] = [h["close"] for h in hist]

    classifications = await _classification_map(db, user_id, {p.symbol for p in stock_positions})

    now = datetime.now(timezone.utc)
    pos_list = []
    for p, mv_chf, cost_chf in valued:
        q_data = quotes.get(p.symbol, {})
        fx = fx_rates.get(p.currency, 1.0)
        td = trade_dates.get(p.symbol, {})
        fx_unavailable = mv_chf is None
        mv_chf = mv_chf or 0.0
        pnl_chf = to_chf((p.unrealized_pnl or 0), p.currency) or 0.0
        last_price_at = _as_aware_utc(p.last_price_at)
        is_stale = p.symbol in failed_symbols and (
            last_price_at is None or (now - last_price_at) > STALE_PRICE_THRESHOLD
        )
        pos_list.append({
            "id": p.id,
            "symbol": p.symbol,
            "name": q_data.get("name", p.name),
            "quantity": p.quantity,
            "avg_cost_price": p.avg_cost_price,
            "currency": p.currency,
            "fx_rate": fx if p.currency != BASE_CCY else None,
            "last_price": p.last_price,
            "last_price_at": p.last_price_at.isoformat() if p.last_price_at else None,
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
            "asset_type": classifications.get(p.symbol, "equity"),
            "price_stale": is_stale,
            "fx_unavailable": fx_unavailable,
        })

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "cash_balance": cash_balance,
        "fx_rates": {k: round(v, 4) for k, v in fx_rates.items()},
        "positions": sorted(pos_list, key=lambda p: p["market_value"], reverse=True),
        "warnings": warnings,
    }


async def get_portfolio(db: AsyncSession, user_id: str) -> dict:
    """Positions with live prices, CHF-converted totals. Persists updated
    last_price/unrealized_pnl on positions and a daily PortfolioSnapshot."""
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user_id)
    )
    positions = result.scalars().all()

    if not positions:
        return {
            "total_value": 0, "total_cost": 0, "total_pnl": 0, "total_pnl_pct": 0,
            "cash_balance": 0, "net_deposits": 0,
            "base_currency": BASE_CCY, "fx_rates": {},
            "positions_count": 0, "positions": [], "warnings": [],
        }

    payload = await _build_holdings_payload(db, user_id, positions)

    # Net deposits (all-time): CASH deposits minus withdrawals. This is the
    # denominator for true all-time P&L — market-value-of-stocks + cash minus
    # the money the user actually put in. Reading from cost-basis would
    # under-report P&L when realised gains have already been booked to cash.
    dep_result = await db.execute(
        select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(and_(
            StockTransaction.user_id == user_id,
            StockTransaction.symbol == "CASH",
            StockTransaction.type == "deposit",
        ))
    )
    wd_result = await db.execute(
        select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(and_(
            StockTransaction.user_id == user_id,
            StockTransaction.symbol == "CASH",
            StockTransaction.type == "withdraw",
        ))
    )
    net_deposits = float(dep_result.scalar() or 0) - float(wd_result.scalar() or 0)

    # Save daily snapshot
    today = date.today()
    snap_result = await db.execute(
        select(PortfolioSnapshot).where(and_(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.snapshot_date == today,
        ))
    )
    snap = snap_result.scalar_one_or_none()
    if snap:
        snap.total_value = payload["total_value"] + payload["cash_balance"]
        snap.total_cost = payload["total_cost"]
        snap.total_pnl = payload["total_pnl"]
    else:
        db.add(PortfolioSnapshot(
            user_id=user_id, total_value=payload["total_value"] + payload["cash_balance"],
            total_cost=payload["total_cost"], total_pnl=payload["total_pnl"],
            snapshot_date=today,
        ))
    await db.commit()

    return {
        **payload,
        "net_deposits": net_deposits,
        "base_currency": BASE_CCY,
        "positions_count": len(payload["positions"]),
    }


async def get_public_portfolio(db: AsyncSession, user_id: str) -> dict:
    """Same valuation core as get_portfolio, shaped for the unauthenticated
    public share view (no net_deposits, no snapshot persistence)."""
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user_id)
    )
    positions = result.scalars().all()

    if not positions:
        return {
            "total_value": 0, "total_cost": 0, "total_pnl": 0, "total_pnl_pct": 0,
            "cash_balance": 0, "base_currency": BASE_CCY,
            "positions_count": 0, "positions": [], "warnings": [],
        }

    payload = await _build_holdings_payload(db, user_id, positions)
    return {
        **payload,
        "base_currency": BASE_CCY,
        "positions_count": len(payload["positions"]),
    }


# ── Trade (buy/sell/deposit/withdraw) ────────────────────────────

async def execute_trade(
    db: AsyncSession,
    user_id: str,
    *,
    symbol: str,
    type: str = "buy",
    quantity: float,
    price: float = 0,
    currency: str = "USD",
    trade_date: str | None = None,
    fees: float = 0,
    deduct_from_cash: bool = True,
    confirm_currency: bool = False,
) -> dict:
    """Record a trade. Supports buy, sell, deposit (cash), withdraw (cash)."""
    account = await get_or_create_brokerage(db, user_id)
    ticker = symbol.upper().strip()
    trade_type = type.lower()
    executed_at = (
        datetime.fromisoformat(trade_date).replace(tzinfo=timezone.utc)
        if trade_date else datetime.now(timezone.utc)
    )

    if trade_type not in ("buy", "sell", "deposit", "withdraw"):
        raise ValueError("Type must be buy, sell, deposit, or withdraw")

    # Handle cash deposit/withdraw
    if trade_type in ("deposit", "withdraw"):
        cash = await get_cash_position(db, user_id, account.id)
        if trade_type == "deposit":
            cash.quantity += quantity
        else:
            if cash.quantity < quantity:
                raise InsufficientCashError(cash.quantity)
            cash.quantity -= quantity

        db.add(StockTransaction(
            user_id=user_id, account_id=account.id,
            symbol="CASH", type=trade_type,
            quantity=quantity, price=1,
            fees=0, currency=currency,
            executed_at=executed_at,
        ))
        await db.commit()
        return {"status": "ok", "cash_balance": cash.quantity}

    # Validate ticker
    if ticker == "CASH":
        raise ValueError("Use deposit/withdraw for cash")

    quote = await get_quote(ticker)
    if not quote:
        raise InvalidTickerError(ticker)

    trade_price = price or quote["price"]
    total_cost = trade_price * quantity + fees

    # Currency check — we never silently overwrite what the user typed.
    # If the quote disagrees, the caller must explicitly confirm the
    # override (confirm_currency=true) before we proceed with the quote's
    # currency; otherwise we reject with enough detail to fix the input.
    yf_ccy = quote.get("currency", "").upper()
    CASH_CCY = "CHF"
    trade_ccy = currency.upper() if currency else ""
    # Normalize user-supplied currency in case it's a subunit code
    trade_ccy, _ = normalize_currency(trade_ccy) if trade_ccy else ("", 1.0)
    if yf_ccy and trade_ccy and trade_ccy != yf_ccy:
        if not confirm_currency:
            raise CurrencyMismatchError(ticker=ticker, user_currency=trade_ccy, quote_currency=yf_ccy)
        logger.info(
            f"execute_trade: user confirmed currency override for {ticker}: "
            f"'{trade_ccy}' -> quote currency '{yf_ccy}'"
        )
        trade_ccy = yf_ccy
    elif not trade_ccy:
        trade_ccy = yf_ccy or "USD"

    if trade_ccy != CASH_CCY:
        fx = await get_fx_rate(trade_ccy, CASH_CCY)
        if fx is None:
            raise FxRateUnavailableError(trade_ccy, CASH_CCY)
    else:
        fx = 1.0
    total_cost_chf = total_cost * fx

    # Get or create position
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user_id,
            StockPosition.symbol == ticker,
        ))
    )
    position = result.scalar_one_or_none()

    if trade_type == "buy":
        # Deduct from cash if enabled (cash is CHF-denominated, convert trade amount)
        if deduct_from_cash:
            cash = await get_cash_position(db, user_id, account.id)
            if cash.quantity < total_cost_chf:
                raise InsufficientCashError(cash.quantity, total_cost_chf)
            cash.quantity -= total_cost_chf

        if position:
            # Update avg cost: weighted average
            old_total = position.avg_cost_price * position.quantity
            new_total = trade_price * quantity
            position.quantity += quantity
            position.avg_cost_price = (old_total + new_total) / position.quantity if position.quantity else 0
        else:
            position = StockPosition(
                user_id=user_id, account_id=account.id,
                symbol=ticker, name=quote.get("name", ticker),
                quantity=quantity, avg_cost_price=trade_price,
                currency=trade_ccy, last_price=quote["price"],
                last_price_at=datetime.now(timezone.utc),
            )
            db.add(position)

    elif trade_type == "sell":
        if not position or position.quantity < quantity:
            raise InsufficientSharesError(position.quantity if position else 0)

        # Add proceeds to cash in CHF (convert from trade currency)
        if deduct_from_cash:
            proceeds_chf = ((trade_price * quantity) - fees) * fx
            cash = await get_cash_position(db, user_id, account.id)
            cash.quantity += proceeds_chf

        position.quantity -= quantity
        if position.quantity <= 0:
            await db.delete(position)

    # Log trade (use corrected trade_ccy, not raw user-supplied currency)
    db.add(StockTransaction(
        user_id=user_id, account_id=account.id,
        symbol=ticker, type=trade_type,
        quantity=quantity, price=trade_price,
        fees=fees, currency=trade_ccy,
        executed_at=executed_at,
    ))

    await db.commit()
    return {
        "status": "ok", "symbol": ticker, "type": trade_type,
        "quantity": quantity, "price": trade_price,
        "currency": trade_ccy,
    }


# ── Trade history / CRUD ─────────────────────────────────────────

async def list_stock_transactions(
    db: AsyncSession, user_id: str, *, symbol: str | None = None, limit: int = 50
) -> list[StockTransaction]:
    query = select(StockTransaction).where(StockTransaction.user_id == user_id)
    if symbol:
        query = query.where(StockTransaction.symbol == symbol.upper())
    query = query.order_by(desc(StockTransaction.executed_at)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_fx_rates_for_trades(trades: list[StockTransaction], base: str = "CHF") -> dict[str, float]:
    """Prefetch FX rates (to `base`) for every distinct trade currency.

    Falls back to a stale cached rate if the live lookup fails; a currency
    genuinely missing from the dict (never known) is left out, and callers
    fall back to displaying 1x for that historical row rather than crashing
    — this is a secondary, backwards-looking display total, not the primary
    CHF totals guarded by get_portfolio()'s warnings contract.
    """
    currencies = {t.currency for t in trades if t.currency != base}
    fx: dict[str, float] = {}
    for ccy in currencies:
        rate = await get_fx_rate(ccy, base)
        if rate is None:
            rate = get_cached_fx_rate(ccy, base)
        if rate is not None:
            fx[ccy] = rate
    return fx


async def update_trade(db: AsyncSession, user_id: str, trade_id: str, updates: dict) -> StockTransaction:
    """Update a stock transaction. `updates` keys: symbol, type, quantity,
    price, fees, currency, date — only non-None values are applied."""
    result = await db.execute(
        select(StockTransaction).where(and_(StockTransaction.id == trade_id, StockTransaction.user_id == user_id))
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise TradeNotFoundError(trade_id)

    if updates.get("symbol") is not None:
        txn.symbol = updates["symbol"].upper().strip()
    if updates.get("type") is not None:
        txn.type = updates["type"]
    if updates.get("quantity") is not None:
        txn.quantity = updates["quantity"]
    if updates.get("price") is not None:
        txn.price = updates["price"]
    if updates.get("fees") is not None:
        txn.fees = updates["fees"]
    if updates.get("currency") is not None:
        txn.currency = updates["currency"]
    if updates.get("date") is not None:
        txn.executed_at = datetime.fromisoformat(updates["date"]).replace(tzinfo=timezone.utc)

    await db.commit()
    return txn


async def delete_trade(db: AsyncSession, user_id: str, trade_id: str) -> None:
    result = await db.execute(
        select(StockTransaction).where(and_(StockTransaction.id == trade_id, StockTransaction.user_id == user_id))
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise TradeNotFoundError(trade_id)
    await db.delete(txn)
    await db.commit()


# ── Position CRUD (direct edit, no trade log) ────────────────────

async def update_position(db: AsyncSession, user_id: str, position_id: str, updates: dict) -> None:
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.id == position_id, StockPosition.user_id == user_id,
        ))
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise PositionNotFoundError(position_id)
    if updates.get("quantity") is not None:
        pos.quantity = updates["quantity"]
    if updates.get("avg_cost_price") is not None:
        pos.avg_cost_price = updates["avg_cost_price"]
    await db.commit()


async def delete_position(db: AsyncSession, user_id: str, position_id: str) -> None:
    result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.id == position_id, StockPosition.user_id == user_id,
        ))
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise PositionNotFoundError(position_id)
    await db.delete(pos)
    await db.commit()


# ── Portfolio value timeline (built from transactions + yfinance) ──

async def build_value_timeline(db: AsyncSession, user_id: str) -> list[dict]:
    """Build day-by-day portfolio value from actual transactions + historical
    prices. Shared by the private dashboard timeline and the public share
    timeline."""
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
        rate = await get_fx_rate(ccy, "CHF")
        if rate is None:
            rate = get_cached_fx_rate(ccy, "CHF")
        if rate is not None:
            fx_rates[ccy] = rate

    def _to_chf(amount: float, ccy: str) -> float:
        # This is a historical timeline reconstruction, not the live totals
        # guarded by get_portfolio()'s warnings contract; a 1x fallback here
        # only bites if we've *never* known this currency's rate at all.
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


# ── Portfolio history (persisted snapshots) ──────────────────────

async def get_portfolio_history(db: AsyncSession, user_id: str, days: int = 90) -> list[dict]:
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(and_(PortfolioSnapshot.user_id == user_id, PortfolioSnapshot.snapshot_date >= since))
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    return [{"date": s.snapshot_date.isoformat(), "value": s.total_value, "pnl": s.total_pnl} for s in result.scalars().all()]
