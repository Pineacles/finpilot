"""Time-weighted return (TWR) of individual stocks vs. a benchmark.

The card on the portfolio page is "is my stock-picking beating SPY?" — so we
chain daily returns on the pre-existing individual-stock holdings and strip
out the effect of when cash went in or out. Index-classified holdings (ETFs,
crypto, etc.) are excluded: the user explicitly wants those not to muddy the
comparison.

Methodology notes
-----------------
* Daily TWR: r_d = (V_end - V_start - net_flow) / V_start, chained.
* V is in CHF. Historical FX conversion uses the current rate as a simplification
  (same approach used in value-timeline — historical FX is a future improvement).
* Only symbols with real StockTransaction rows are counted. Saxo-synced-only
  positions (no entry date) are listed separately as caveats.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction
from app.services import classification as classification_svc
from app.services.prices import get_fx_rate, get_history

logger = logging.getLogger(__name__)

RangeKey = Literal["1W", "1M", "3M", "YTD", "1Y", "ALL", "CUSTOM"]


@dataclass
class CountedSymbol:
    symbol: str
    asset_type: str
    source: str  # auto|user|agent
    quantity: float
    first_tx_date: str


@dataclass
class ExcludedSymbol:
    symbol: str
    asset_type: str
    source: str
    reason: str  # classified_non_equity | no_transactions | saxo_only


@dataclass
class BenchmarkResult:
    range: str
    start_date: str
    end_date: str
    benchmark_symbol: str
    portfolio_series: list[dict]
    benchmark_series: list[dict]
    summary: dict
    counted_symbols: list[dict] = field(default_factory=list)
    excluded_symbols: list[dict] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


def _resolve_range(range_key: str, custom_start: str | None, custom_end: str | None) -> tuple[date, date]:
    today = date.today()
    key = (range_key or "1M").upper()
    if key == "CUSTOM":
        if not custom_start or not custom_end:
            raise ValueError("custom range requires start and end")
        return (date.fromisoformat(custom_start), date.fromisoformat(custom_end))
    if key == "1W":
        return (today - timedelta(days=7), today)
    if key == "1M":
        return (today - timedelta(days=30), today)
    if key == "3M":
        return (today - timedelta(days=90), today)
    if key == "YTD":
        return (date(today.year, 1, 1), today)
    if key == "1Y":
        return (today - timedelta(days=365), today)
    if key == "ALL":
        # Caller handles ALL specially — needs first tx date
        return (date(1970, 1, 1), today)
    raise ValueError(f"unknown range: {range_key}")


def _yf_range_for_days(days: int) -> str:
    if days <= 7:
        return "1mo"   # minimum 1mo — yfinance's 5d often has gaps at boundaries
    if days <= 30:
        return "1mo"
    if days <= 90:
        return "3mo"
    if days <= 180:
        return "6mo"
    if days <= 365:
        return "1y"
    if days <= 730:
        return "2y"
    if days <= 1825:
        return "5y"
    return "max"


def _lookup_price_on_or_before(history: dict[str, float], d: str) -> float | None:
    """Return price for date d, or most recent available before d."""
    if d in history:
        return history[d]
    prior = [k for k in history.keys() if k <= d]
    if not prior:
        return None
    return history[max(prior)]


async def _saxo_account_ids(db: AsyncSession, user_id: str) -> set[str]:
    """IDs of local accounts that are Saxo-sourced (so we can flag them)."""
    try:
        from app.brokers.saxo import sync as saxo_sync
        prefix = saxo_sync.SAXO_ACCOUNT_NAME_PREFIX
    except Exception:
        prefix = "Saxo "

    result = await db.execute(
        select(Account.id).where(and_(
            Account.user_id == user_id,
            Account.name.like(f"{prefix}%"),
        ))
    )
    return {row for row in result.scalars().all()}


async def compute_benchmark_comparison(
    db: AsyncSession,
    user_id: str,
    range_key: str = "1M",
    benchmark_symbol: str = "SPY",
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> BenchmarkResult:
    """Compute TWR of individual-stock holdings vs. the benchmark.

    Only equities are counted. ETFs/index/crypto classified holdings are excluded.
    Saxo-synced positions without StockTransaction rows are excluded with a caveat.
    """
    start_date, end_date = _resolve_range(range_key, custom_start, custom_end)

    # All transactions up to end_date (we need full history to reconstruct holdings at start_date)
    result = await db.execute(
        select(StockTransaction)
        .where(and_(
            StockTransaction.user_id == user_id,
            StockTransaction.symbol != "CASH",
        ))
        .order_by(StockTransaction.executed_at)
    )
    all_txs = list(result.scalars().all())

    if not all_txs:
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary={"portfolio_return_pct": 0.0, "benchmark_return_pct": 0.0, "alpha_pct": 0.0},
            caveats=["No stock transactions recorded yet — log trades to build a benchmark comparison."],
        )

    # ALL resolves to first-tx-date → today
    if range_key.upper() == "ALL":
        start_date = all_txs[0].executed_at.date()

    # Classify every symbol touched (auto-classify any unknowns so UI shows them too)
    all_symbols = sorted({t.symbol for t in all_txs})
    asset_types = await classification_svc.get_asset_types_bulk(db, user_id, all_symbols)
    # Any symbol not yet classified — try to auto-classify synchronously in bulk
    for sym in all_symbols:
        if asset_types.get(sym) == classification_svc.DEFAULT_ASSET_TYPE:
            existing = await classification_svc.get_classification(db, user_id, sym)
            if existing is None:
                try:
                    row = await classification_svc.ensure_classified(db, user_id, sym)
                    asset_types[sym] = row.asset_type
                except Exception as e:
                    logger.warning(f"auto-classify failed for {sym}: {e}")

    # Split symbols
    equity_symbols = {s for s in all_symbols if asset_types.get(s) == "equity"}
    excluded: list[ExcludedSymbol] = []
    for s in all_symbols:
        at = asset_types.get(s, "equity")
        if at != "equity":
            source = "auto"
            row = await classification_svc.get_classification(db, user_id, s)
            if row:
                source = row.source
            excluded.append(ExcludedSymbol(
                symbol=s, asset_type=at, source=source, reason="classified_non_equity",
            ))

    # Saxo-only positions (held but no tx history) — flag as caveats, not counted
    saxo_ids = await _saxo_account_ids(db, user_id)
    tx_symbols = {t.symbol for t in all_txs}
    pos_result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user_id,
            StockPosition.symbol != "CASH",
            StockPosition.quantity > 0,
        ))
    )
    saxo_only_count = 0
    for p in pos_result.scalars().all():
        if p.symbol not in tx_symbols and p.account_id in saxo_ids:
            saxo_only_count += 1
            excluded.append(ExcludedSymbol(
                symbol=p.symbol,
                asset_type=asset_types.get(p.symbol, "equity"),
                source=(await classification_svc.get_classification(db, user_id, p.symbol)).source
                if await classification_svc.get_classification(db, user_id, p.symbol) else "auto",
                reason="saxo_only",
            ))

    # Scoped trades for the TWR walk
    equity_txs = [t for t in all_txs if t.symbol in equity_symbols]
    if not equity_txs:
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary={"portfolio_return_pct": 0.0, "benchmark_return_pct": 0.0, "alpha_pct": 0.0},
            excluded_symbols=[e.__dict__ for e in excluded],
            caveats=["No individual-stock transactions in scope (all classified as ETF/index/other)."],
        )

    # Fetch historical prices for all equity symbols + benchmark
    days_needed = (end_date - equity_txs[0].executed_at.date()).days + 1
    yf_range = _yf_range_for_days(days_needed)

    # Per-symbol history in native currency
    price_history: dict[str, dict[str, float]] = {}
    sym_ccy: dict[str, str] = {}
    for sym in equity_symbols:
        hist = await get_history(sym, range=yf_range, interval="1d")
        price_history[sym] = {h["date"]: h["close"] for h in hist}

    for t in equity_txs:
        sym_ccy.setdefault(t.symbol, t.currency.upper())

    # FX rates to CHF (current rates — historical FX out of scope, same as value-timeline)
    fx_rates: dict[str, float] = {}
    for ccy in set(sym_ccy.values()):
        fx_rates[ccy] = await get_fx_rate(ccy, "CHF")

    def _to_chf(amount: float, ccy: str) -> float:
        return amount * fx_rates.get(ccy.upper(), 1.0)

    # Benchmark history
    bench_hist_raw = await get_history(benchmark_symbol, range=yf_range, interval="1d")
    bench_prices: dict[str, float] = {h["date"]: h["close"] for h in bench_hist_raw}

    # Date axis: every date from start_date to end_date. We only emit days where
    # we have at least one price point (weekdays with data).
    all_dates: set[str] = set()
    for prices in price_history.values():
        all_dates.update(prices.keys())
    all_dates.update(bench_prices.keys())
    # Plus any transaction date in scope
    for t in equity_txs:
        all_dates.add(t.executed_at.date().isoformat())
    if not all_dates:
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary={"portfolio_return_pct": 0.0, "benchmark_return_pct": 0.0, "alpha_pct": 0.0},
            excluded_symbols=[e.__dict__ for e in excluded],
            caveats=["Price history unavailable for this range."],
        )

    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    sorted_dates = sorted(d for d in all_dates if d <= end_iso)

    # Walk all history to reconstruct holdings at start_date, then begin recording.
    holdings: dict[str, float] = {}
    tx_idx = 0
    portfolio_index = 100.0
    v_prev_end = 0.0  # end-of-previous-day CHF value
    portfolio_points: list[dict] = []
    benchmark_points: list[dict] = []
    benchmark_index = 100.0
    bench_prev_price: float | None = None
    counted_first_tx: dict[str, str] = {}

    recording = False  # becomes True once we reach start_date

    for d in sorted_dates:
        # Apply trades whose executed_at date is <= d (in order)
        while tx_idx < len(equity_txs):
            t = equity_txs[tx_idx]
            td = t.executed_at.date().isoformat()
            if td > d:
                break
            if t.type == "buy":
                holdings[t.symbol] = holdings.get(t.symbol, 0) + t.quantity
            elif t.type == "sell":
                holdings[t.symbol] = max(0.0, holdings.get(t.symbol, 0) - t.quantity)
            counted_first_tx.setdefault(t.symbol, td)
            tx_idx += 1

        # Net flow in CHF for trades on day d (buy: positive, sell: negative)
        day_flow = 0.0
        for t in equity_txs:
            if t.executed_at.date().isoformat() != d:
                continue
            ccy = t.currency.upper()
            if t.type == "buy":
                day_flow += _to_chf(t.quantity * t.price + t.fees, ccy)
            elif t.type == "sell":
                day_flow -= _to_chf(t.quantity * t.price - t.fees, ccy)

        # End-of-day value in CHF (uses d's close, or most recent prior close)
        v_end = 0.0
        for sym, qty in holdings.items():
            if qty <= 0:
                continue
            price = _lookup_price_on_or_before(price_history.get(sym, {}), d)
            if price is None:
                continue
            v_end += _to_chf(qty * price, sym_ccy.get(sym, "USD"))

        # Daily TWR — only valid if we had pre-existing holdings (v_prev_end > 0)
        if recording or d >= start_iso:
            if not recording:
                # First recording day — anchor the index at 100
                recording = True
                if d > start_iso:
                    # If the first price point is after start_date, still anchor here
                    pass
                portfolio_points.append({"date": d, "index": 100.0, "value_chf": round(v_end, 2)})
                bp = bench_prices.get(d) or _lookup_price_on_or_before(bench_prices, d)
                if bp is not None:
                    bench_prev_price = bp
                    benchmark_points.append({"date": d, "index": 100.0, "close": round(bp, 4)})
            else:
                # Chain portfolio return
                if v_prev_end > 0:
                    r = (v_end - v_prev_end - day_flow) / v_prev_end
                    portfolio_index *= (1 + r)
                portfolio_points.append({"date": d, "index": round(portfolio_index, 4), "value_chf": round(v_end, 2)})

                # Chain benchmark return
                bp = bench_prices.get(d) or _lookup_price_on_or_before(bench_prices, d)
                if bp is not None:
                    if bench_prev_price and bench_prev_price > 0:
                        br = (bp - bench_prev_price) / bench_prev_price
                        benchmark_index *= (1 + br)
                    bench_prev_price = bp
                    benchmark_points.append({"date": d, "index": round(benchmark_index, 4), "close": round(bp, 4)})

        v_prev_end = v_end

    # Summary
    portfolio_return_pct = (portfolio_points[-1]["index"] - 100.0) if portfolio_points else 0.0
    benchmark_return_pct = (benchmark_points[-1]["index"] - 100.0) if benchmark_points else 0.0
    alpha_pct = round(portfolio_return_pct - benchmark_return_pct, 4)

    # Counted symbols (with final quantity in window end + first-tx date)
    counted: list[CountedSymbol] = []
    for sym in sorted(equity_symbols):
        qty = holdings.get(sym, 0.0)
        first_date = counted_first_tx.get(sym, "")
        cls_row = await classification_svc.get_classification(db, user_id, sym)
        counted.append(CountedSymbol(
            symbol=sym,
            asset_type=asset_types.get(sym, "equity"),
            source=cls_row.source if cls_row else "auto",
            quantity=round(qty, 6),
            first_tx_date=first_date,
        ))

    caveats: list[str] = []
    if saxo_only_count:
        caveats.append(
            f"{saxo_only_count} Saxo-synced position(s) excluded — no transaction history to anchor entry date. "
            "Log trades manually or the broker's reported avg cost to include them."
        )

    return BenchmarkResult(
        range=range_key,
        start_date=start_iso,
        end_date=end_iso,
        benchmark_symbol=benchmark_symbol,
        portfolio_series=portfolio_points,
        benchmark_series=benchmark_points,
        summary={
            "portfolio_return_pct": round(portfolio_return_pct, 4),
            "benchmark_return_pct": round(benchmark_return_pct, 4),
            "alpha_pct": alpha_pct,
        },
        counted_symbols=[c.__dict__ for c in counted],
        excluded_symbols=[e.__dict__ for e in excluded],
        caveats=caveats,
    )
