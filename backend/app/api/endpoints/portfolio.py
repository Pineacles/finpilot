"""Portfolio endpoints: positions, trades, cash, live prices, charts.

Business logic (valuation, trade execution, CRUD) lives in
app.services.portfolio_service; this router just parses/validates requests,
calls the service, and shapes HTTP responses/errors.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.stock import StockPosition
from app.models.user import User
from app.services.prices import get_history
from app.services import portfolio_service
from app.services.portfolio_service import (
    PositionNotFoundError,
    InsufficientCashError,
    InsufficientSharesError,
    InvalidTickerError,
    CurrencyMismatchError,
    FxRateUnavailableError,
    suggest_ticker_suffix,
)
from app.schemas.portfolio import (
    PortfolioResponse,
    TradeExecutionResponse,
    TradeHistoryItem,
    ValueTimelinePoint,
    PortfolioHistoryPoint,
    ClassificationOut,
    PublicShareStatusResponse,
)

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
    confirm_currency: bool = False  # true = "yes, use the quote's currency" after a 422 currency_mismatch


class UpdatePosition(BaseModel):
    quantity: float | None = None
    avg_cost_price: float | None = None


# ── Portfolio overview with live prices ──────────────────────────

@router.get("", response_model=PortfolioResponse)
async def get_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await portfolio_service.get_portfolio(db, user.id)


# ── Trade (buy/sell/deposit/withdraw) ────────────────────────────

@router.post("/trade", response_model=TradeExecutionResponse, response_model_exclude_none=True)
@router.post("/trades", response_model=TradeExecutionResponse, response_model_exclude_none=True)
async def execute_trade(
    body: TradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a trade. Supports buy, sell, deposit (cash), withdraw (cash)."""
    try:
        return await portfolio_service.execute_trade(
            db, user.id,
            symbol=body.symbol, type=body.type, quantity=body.quantity,
            price=body.price, currency=body.currency, trade_date=body.date,
            fees=body.fees, deduct_from_cash=body.deduct_from_cash,
            confirm_currency=body.confirm_currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidTickerError as e:
        raise HTTPException(status_code=400, detail=f"Ticker {e.ticker} not found")
    except CurrencyMismatchError as e:
        raise HTTPException(status_code=422, detail=_currency_mismatch_detail(e))
    except FxRateUnavailableError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Exchange rate for {e.from_ccy}→{e.to_ccy} is currently unavailable. Try again shortly.",
        )
    except InsufficientCashError as e:
        if e.needed is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient cash: {e.available:.2f} CHF, need {e.needed:.2f} CHF. Deposit cash first or disable deduct_from_cash."
            )
        raise HTTPException(status_code=400, detail=f"Insufficient cash: {e.available:.2f}")
    except InsufficientSharesError as e:
        raise HTTPException(status_code=400, detail=f"Insufficient shares: {e.available}")


def _currency_mismatch_detail(e: CurrencyMismatchError) -> dict:
    """Shape a 422 detail body the trade dialog can render directly: the
    message, plus structured fields for a 'use {quote_currency} instead'
    confirm button."""
    suggested_ticker = suggest_ticker_suffix(e.ticker, e.quote_currency)
    message = (
        f"You entered {e.user_currency} for {e.ticker}, but its market quote is denominated "
        f"in {e.quote_currency}."
    )
    if suggested_ticker:
        message += f" If you meant the {e.quote_currency} listing, the ticker is usually '{suggested_ticker}'."
    message += f" Confirm to record this trade in {e.quote_currency} instead, or fix the ticker/currency."
    return {
        "error": "currency_mismatch",
        "message": message,
        "ticker": e.ticker,
        "user_currency": e.user_currency,
        "quote_currency": e.quote_currency,
        "suggested_ticker": suggested_ticker,
    }


# ── Trade history ────────────────────────────────────────────────

@router.get("/trades", response_model=list[TradeHistoryItem])
async def get_trades(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trades = await portfolio_service.list_stock_transactions(db, user.id, symbol=symbol, limit=limit)
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


# ── CRUD (direct edit, no trade log) ────────────────────────────

@router.patch("/{position_id}")
async def update_position(
    position_id: str,
    body: UpdatePosition,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await portfolio_service.update_position(db, user.id, position_id, body.model_dump())
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"status": "ok"}


@router.delete("/{position_id}")
async def delete_position(
    position_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await portfolio_service.delete_position(db, user.id, position_id)
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found")
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

@router.get("/value-timeline", response_model=list[ValueTimelinePoint])
async def get_value_timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build day-by-day portfolio value from actual transactions + historical prices."""
    return await portfolio_service.build_value_timeline(db, user.id)


class ClassifyRequest(BaseModel):
    asset_type: str  # equity|etf|index|crypto|bond|commodity|cash


@router.get("/classifications", response_model=list[ClassificationOut])
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
    from app.services.prices import get_quotes_batch

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
            # Broker-side failure: fall back to yfinance for all symbols.
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

@router.get("/history", response_model=list[PortfolioHistoryPoint])
async def get_portfolio_history(
    days: int = 90,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await portfolio_service.get_portfolio_history(db, user.id, days=days)


# ── Public sharing ──────────────────────────────────────────────

@router.get("/public/status", response_model=PublicShareStatusResponse)
async def get_public_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"enabled": user.public_portfolio, "token": user.public_share_token}


@router.post("/public/toggle", response_model=PublicShareStatusResponse)
async def toggle_public_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.public_portfolio:
        # Turning off: clear the token so old links stop working
        user.public_portfolio = False
        user.public_share_token = None
    else:
        # Turning on: generate a fresh token
        user.public_portfolio = True
        user.public_share_token = secrets.token_urlsafe(32)
    await db.commit()
    return {"enabled": user.public_portfolio, "token": user.public_share_token}
