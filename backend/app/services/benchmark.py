"""TWR (Time-Weighted Return) on active-period holdings vs. a benchmark.

Methodology: "how did my stocks do during the time I actually held them?"
-----------
For each calendar day d in [walk_start, end_date]:
  1. Apply equity transactions executed on d (buy adds qty, sell removes qty).
  2. Compute portfolio value at d's closing prices (CHF).
  3. If portfolio was non-zero yesterday, compute daily return as:
       r_d = (V_d - V_prev - flow_d) / V_prev
     and chain it into the running index.
  4. Anchor both portfolio and benchmark at 100 on the first day the portfolio
     has a non-zero value (the first "active" day).
  5. After all holdings are closed the index stays flat — it records what was
     earned during the active period only.

counted_symbols: any equity symbol with tx activity during [start, end] that
  was held for at least one day within the window.

excluded_symbols:
  classified_non_equity — held/transacted but not classified as equity.
  saxo_only             — Saxo-synced position with no transaction history.
  closed_before_window  — symbol has txs but last sale happened before start_date.
"""
from __future__ import annotations

import copy
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
    source: str           # auto|user|agent
    active_from: str      # ISO date — first day held in window
    active_to: str | None # ISO date — last day held, or None if still held at end_date
    current_qty: float
    contribution_pp: float
    # Legacy fields kept for backward-compat
    quantity: float = 0.0
    first_tx_date: str = ""


@dataclass
class ExcludedSymbol:
    symbol: str
    asset_type: str
    source: str
    reason: str  # classified_non_equity | saxo_only | closed_before_window | closed


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
        return (date(1970, 1, 1), today)
    raise ValueError(f"unknown range: {range_key}")


def _yf_range_for_days(days: int) -> str:
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
    """IDs of local accounts that are Saxo-sourced."""
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
    """Compute TWR-on-active-periods for equity holdings vs. benchmark.

    For each day the portfolio was actually invested, we chain the daily return.
    Stocks bought mid-window are anchored from their first active day; sold
    stocks stop contributing after the sale day. Benchmark is anchored at the
    same first-active day so comparisons are fair.
    """
    start_date, end_date = _resolve_range(range_key, custom_start, custom_end)

    # --- Fetch current stock positions ---
    pos_result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user_id,
            StockPosition.symbol != "CASH",
        ))
    )
    all_positions = list(pos_result.scalars().all())

    # --- Fetch all transaction history ---
    tx_result = await db.execute(
        select(StockTransaction).where(and_(
            StockTransaction.user_id == user_id,
            StockTransaction.symbol != "CASH",
        )).order_by(StockTransaction.executed_at)
    )
    all_txs = list(tx_result.scalars().all())

    # ALL resolves to first-tx-date → today
    if range_key.upper() == "ALL" and all_txs:
        start_date = all_txs[0].executed_at.date()

    if not all_txs and not all_positions:
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary=_zero_summary(),
            caveats=["No stock transactions recorded yet — log trades to build a benchmark comparison."],
        )

    if not all_txs:
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary=_zero_summary(),
            caveats=["No stock transactions recorded yet — log trades to build a benchmark comparison."],
        )

    # Build symbol lookups
    tx_symbols: set[str] = {t.symbol for t in all_txs}
    sym_ccy: dict[str, str] = {}
    first_tx_date: dict[str, str] = {}
    for t in all_txs:
        sym_ccy.setdefault(t.symbol, t.currency.upper())
        if t.type == "buy":
            d = t.executed_at.date().isoformat()
            existing = first_tx_date.get(t.symbol)
            if existing is None or d < existing:
                first_tx_date[t.symbol] = d

    # Classify every symbol touched by transactions
    all_tx_symbols = sorted(tx_symbols)
    asset_types = await classification_svc.get_asset_types_bulk(db, user_id, all_tx_symbols)
    for sym in all_tx_symbols:
        if asset_types.get(sym) == classification_svc.DEFAULT_ASSET_TYPE:
            existing = await classification_svc.get_classification(db, user_id, sym)
            if existing is None:
                try:
                    row = await classification_svc.ensure_classified(db, user_id, sym)
                    asset_types[sym] = row.asset_type
                except Exception as e:
                    logger.warning(f"auto-classify failed for {sym}: {e}")

    # Classify symbols in positions with no tx history (saxo-only)
    pos_symbols_no_tx = [p.symbol for p in all_positions if p.symbol not in tx_symbols]
    if pos_symbols_no_tx:
        extra_types = await classification_svc.get_asset_types_bulk(db, user_id, pos_symbols_no_tx)
        asset_types.update(extra_types)

    saxo_ids = await _saxo_account_ids(db, user_id)

    # Current qty from StockPosition rows
    current_qty: dict[str, float] = {}
    for p in all_positions:
        current_qty[p.symbol] = current_qty.get(p.symbol, 0.0) + (p.quantity or 0.0)

    async def _get_source(sym: str) -> str:
        cls_row = await classification_svc.get_classification(db, user_id, sym)
        return cls_row.source if cls_row else "auto"

    # --- Determine which equity symbols to walk ---
    # Filter: only equity-classified symbols that have any tx
    equity_tx_symbols: set[str] = {
        s for s in tx_symbols if asset_types.get(s, "equity") == "equity"
    }

    # For each equity symbol determine last day it had any holdings
    # to detect "closed_before_window"
    # We need to simulate holdings up to start_date to see if they were closed
    def _last_active_date(sym: str) -> date | None:
        """Replay txs for sym and return the last date qty went from >0 to 0 (sell),
        or today if still held."""
        qty = 0.0
        last_active = None
        for t in all_txs:
            if t.symbol != sym:
                continue
            if t.type == "buy":
                qty += t.quantity
                last_active = t.executed_at.date()
            elif t.type == "sell":
                qty = max(0.0, qty - t.quantity)
                last_active = t.executed_at.date()
        # if qty > 0 at end, it's still active → last active = today
        if qty > 0:
            return date.today()
        return last_active

    # Build excluded list
    excluded: list[ExcludedSymbol] = []

    # Non-equity tx symbols
    for sym in all_tx_symbols:
        at = asset_types.get(sym, "equity")
        if at != "equity":
            excluded.append(ExcludedSymbol(
                symbol=sym, asset_type=at,
                source=await _get_source(sym),
                reason="classified_non_equity",
            ))

    # Equity tx symbols: check if closed before window
    closed_before_window_symbols: set[str] = set()
    for sym in equity_tx_symbols:
        last_active = _last_active_date(sym)
        if last_active is not None and last_active < start_date:
            closed_before_window_symbols.add(sym)
            excluded.append(ExcludedSymbol(
                symbol=sym, asset_type="equity",
                source=await _get_source(sym),
                reason="closed_before_window",
            ))

    # Saxo-only positions
    saxo_only_count = 0
    for p in all_positions:
        if p.symbol in tx_symbols:
            continue
        if p.account_id in saxo_ids and (p.quantity or 0) > 0:
            saxo_only_count += 1
            excluded.append(ExcludedSymbol(
                symbol=p.symbol,
                asset_type=asset_types.get(p.symbol, "equity"),
                source=await _get_source(p.symbol),
                reason="saxo_only",
            ))

    # Active equity symbols: equity with txs AND not closed before window
    active_equity_symbols: set[str] = equity_tx_symbols - closed_before_window_symbols

    if not active_equity_symbols:
        closed_bw = sum(1 for e in excluded if e.reason == "closed_before_window")
        caveats_base: list[str] = []
        if closed_bw:
            caveats_base.append(
                f"{closed_bw} symbol(s) were sold out before this window started (see Excluded)."
            )
        caveats_base.append("No individual-stock positions held during this window (all closed or classified as ETF/index/other).")
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary=_zero_summary(),
            excluded_symbols=[e.__dict__ for e in excluded],
            caveats=caveats_base,
        )

    # --- Fetch price histories ---
    # Walk starts from earliest tx to reconstruct holdings at start_date correctly
    earliest_tx_date = min(t.executed_at.date() for t in all_txs)
    walk_start = min(earliest_tx_date, start_date)
    days_to_cover = (end_date - walk_start).days + 30

    yf_range = _yf_range_for_days(days_to_cover)

    price_history: dict[str, dict[str, float]] = {}
    for sym in active_equity_symbols:
        hist = await get_history(sym, range=yf_range, interval="1d")
        price_history[sym] = {h["date"]: h["close"] for h in hist}
        if sym not in sym_ccy:
            p_match = next((p for p in all_positions if p.symbol == sym), None)
            if p_match and p_match.currency:
                sym_ccy[sym] = p_match.currency.upper()
            else:
                sym_ccy[sym] = "USD"

    bench_hist_raw = await get_history(benchmark_symbol, range=yf_range, interval="1d")
    bench_prices: dict[str, float] = {h["date"]: h["close"] for h in bench_hist_raw}

    # FX rates to CHF
    fx_rates: dict[str, float] = {}
    all_ccys = set(sym_ccy.get(s, "USD") for s in active_equity_symbols)
    for ccy in all_ccys:
        fx_rates[ccy] = await get_fx_rate(ccy, "CHF")

    def _to_chf(amount: float, ccy: str) -> float:
        return amount * fx_rates.get(ccy.upper(), 1.0)

    # Group equity txs by date
    equity_txs = [t for t in all_txs if t.symbol in active_equity_symbols]
    txs_by_date: dict[str, list] = {}
    for t in equity_txs:
        d = t.executed_at.date().isoformat()
        txs_by_date.setdefault(d, []).append(t)

    # --- Walk every calendar day from walk_start to end_date ---
    holdings: dict[str, float] = {}     # symbol -> qty
    holdings_prev: dict[str, float] = {}
    V_prev = 0.0
    port_index: float | None = None
    bench_index: float | None = None
    bench_prev_close: float | None = None

    portfolio_points: list[dict] = []
    benchmark_points: list[dict] = []
    per_sym_contrib_total: dict[str, float] = {}  # cumulative contribution_pp per symbol
    active_from_sym: dict[str, str] = {}   # first day held in window
    active_to_sym: dict[str, str] = {}     # last day held in window

    daily_alpha_samples: list[float] = []
    days_portfolio_ahead = 0
    total_days_compared = 0

    n_days = (end_date - walk_start).days + 1

    for i in range(n_days):
        d = walk_start + timedelta(days=i)
        d_iso = d.isoformat()
        in_window = start_date <= d <= end_date

        # Apply today's transactions
        day_flow_chf = 0.0
        syms_sold_today: set[str] = set()
        for t in txs_by_date.get(d_iso, []):
            ccy = sym_ccy.get(t.symbol, "USD")
            if t.type == "buy":
                holdings[t.symbol] = holdings.get(t.symbol, 0.0) + t.quantity
                day_flow_chf += _to_chf((t.quantity * t.price) + (t.fees or 0.0), ccy)
            elif t.type == "sell":
                holdings[t.symbol] = max(0.0, holdings.get(t.symbol, 0.0) - t.quantity)
                day_flow_chf -= _to_chf((t.quantity * t.price) - (t.fees or 0.0), ccy)
                syms_sold_today.add(t.symbol)

        # Value at end-of-day
        V_d = 0.0
        per_sym_value: dict[str, float] = {}
        for sym, qty in holdings.items():
            if qty <= 0:
                continue
            price = _lookup_price_on_or_before(price_history.get(sym, {}), d_iso)
            if price is None:
                continue
            val = _to_chf(qty * price, sym_ccy.get(sym, "USD"))
            V_d += val
            per_sym_value[sym] = val
            if in_window:
                active_from_sym.setdefault(sym, d_iso)
                active_to_sym[sym] = d_iso

        # Mark sell-day as active_to for symbols fully sold today (qty -> 0 at EoD)
        if in_window:
            for sym in syms_sold_today:
                if holdings.get(sym, 0.0) <= 0:
                    # Symbol was closed today — the sell day is the last active day
                    if sym in active_from_sym:  # only if it was ever active in window
                        active_to_sym[sym] = d_iso

        # Daily return and per-stock contributors
        r_d = 0.0
        contributors_pp: dict[str, float] = {}
        if V_prev > 0:
            r_d = (V_d - V_prev - day_flow_chf) / V_prev
            # Per-stock contribution based on yesterday's holdings
            for sym, qty_prev in holdings_prev.items():
                if qty_prev <= 0:
                    continue
                p_prev_d = (d - timedelta(days=1)).isoformat()
                p_prev = _lookup_price_on_or_before(price_history.get(sym, {}), p_prev_d)
                p_today = _lookup_price_on_or_before(price_history.get(sym, {}), d_iso)
                if p_prev is None or p_today is None:
                    continue
                contrib = qty_prev * (p_today - p_prev) * fx_rates.get(sym_ccy.get(sym, "USD"), 1.0) / V_prev * 100.0
                if abs(contrib) > 1e-6:
                    contributors_pp[sym] = round(contrib, 4)

        # Anchor logic — only emit points within window
        if in_window:
            if port_index is None and V_d > 0:
                # First active day: anchor both at 100
                port_index = 100.0
                bench_p = _lookup_price_on_or_before(bench_prices, d_iso)
                if bench_p:
                    bench_index = 100.0
                    bench_prev_close = bench_p
                portfolio_points.append({
                    "date": d_iso, "index": 100.0, "value_chf": round(V_d, 2), "contributors": {},
                })
                if bench_p:
                    benchmark_points.append({
                        "date": d_iso, "index": 100.0, "close": round(bench_p, 4),
                    })
            elif port_index is not None:
                # Chain portfolio return
                if V_prev > 0:
                    port_index = port_index * (1.0 + r_d)
                # (if V_prev == 0 and port_index is not None: flat — holdings exhausted and back to 0)

                portfolio_points.append({
                    "date": d_iso, "index": round(port_index, 4),
                    "value_chf": round(V_d, 2), "contributors": contributors_pp,
                })
                # Accumulate per-symbol contributions in window
                for s, c in contributors_pp.items():
                    per_sym_contrib_total[s] = per_sym_contrib_total.get(s, 0.0) + c

                # Benchmark chain
                bench_p = _lookup_price_on_or_before(bench_prices, d_iso)
                if bench_p is not None and bench_index is not None:
                    if bench_prev_close and bench_prev_close > 0:
                        br = (bench_p - bench_prev_close) / bench_prev_close
                        bench_index = bench_index * (1.0 + br)
                        if V_prev > 0:
                            daily_alpha_samples.append(r_d - br)
                            total_days_compared += 1
                            if port_index > bench_index:
                                days_portfolio_ahead += 1
                    bench_prev_close = bench_p
                    benchmark_points.append({
                        "date": d_iso, "index": round(bench_index, 4), "close": round(bench_p, 4),
                    })
            # else: before anchor — don't emit (portfolio hasn't started yet)

        # Advance state
        holdings_prev = copy.copy(holdings)
        V_prev = V_d

    # --- Build counted_symbols (had active holdings in window) ---
    counted: list[CountedSymbol] = []
    for sym in sorted(active_from_sym.keys()):
        cls_row = await classification_svc.get_classification(db, user_id, sym)
        src = cls_row.source if cls_row else "auto"
        # active_to is None if still held at end_date (last active == end_date and qty > 0)
        last_active = active_to_sym.get(sym, start_date.isoformat())
        cur_qty = current_qty.get(sym, 0.0)
        is_still_held = cur_qty > 0 and last_active == end_date.isoformat()
        counted.append(CountedSymbol(
            symbol=sym,
            asset_type=asset_types.get(sym, "equity"),
            source=src,
            active_from=active_from_sym[sym],
            active_to=None if is_still_held else last_active,
            current_qty=round(cur_qty, 6),
            contribution_pp=round(per_sym_contrib_total.get(sym, 0.0), 4),
            quantity=round(cur_qty, 6),
            first_tx_date=first_tx_date.get(sym, ""),
        ))

    # Also add equity symbols that were active somewhere in the window but had no
    # price-data hits (active_from_sym tracks price-based hits; a symbol with txs
    # in window but no price data wouldn't appear). We add them to excluded instead.
    symbols_with_txs_in_window = {
        t.symbol for t in equity_txs
        if start_date <= t.executed_at.date() <= end_date
    }
    for sym in symbols_with_txs_in_window - active_from_sym.keys() - {e.symbol for e in excluded}:
        excluded.append(ExcludedSymbol(
            symbol=sym, asset_type="equity",
            source=await _get_source(sym),
            reason="classified_non_equity",
        ))

    if not portfolio_points:
        # No active period detected within window
        closed_bw = sum(1 for e in excluded if e.reason == "closed_before_window")
        caveats_out: list[str] = []
        if closed_bw:
            caveats_out.append(
                f"{closed_bw} symbol(s) were sold out before this window started (see Excluded)."
            )
        caveats_out.append("No active holdings within this window — nothing to chart.")
        return BenchmarkResult(
            range=range_key, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            benchmark_symbol=benchmark_symbol, portfolio_series=[], benchmark_series=[],
            summary=_zero_summary(),
            counted_symbols=[c.__dict__ for c in counted],
            excluded_symbols=[e.__dict__ for e in excluded],
            caveats=caveats_out,
        )

    # Summary stats
    port_return = portfolio_points[-1]["index"] - 100.0
    bench_return = benchmark_points[-1]["index"] - 100.0 if benchmark_points else 0.0
    alpha = port_return - bench_return
    avg_daily_alpha = (sum(daily_alpha_samples) / len(daily_alpha_samples) * 100.0) if daily_alpha_samples else 0.0

    # Caveats
    caveats: list[str] = [
        "Line shows TWR during active holding periods — only counts days the stock was actually held.",
    ]
    closed_bw_count = sum(1 for e in excluded if e.reason == "closed_before_window")
    if closed_bw_count:
        caveats.append(
            f"{closed_bw_count} symbol(s) were fully sold out before this window started (see Excluded)."
        )
    closed_count = sum(1 for e in excluded if e.reason == "closed")
    if closed_count:
        caveats.append(
            f"{closed_count} symbol(s) sold out during or before this window aren't counted (see Excluded)."
        )
    if saxo_only_count:
        caveats.append(
            f"{saxo_only_count} Saxo-synced position(s) excluded — no transaction history to anchor entry date. "
            "Log trades manually to include them."
        )

    return BenchmarkResult(
        range=range_key,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        benchmark_symbol=benchmark_symbol,
        portfolio_series=portfolio_points,
        benchmark_series=benchmark_points,
        summary={
            "portfolio_return_pct": round(port_return, 4),
            "benchmark_return_pct": round(bench_return, 4),
            "alpha_pct": round(alpha, 4),
            "avg_daily_alpha_pp": round(avg_daily_alpha, 4),
            "days_portfolio_ahead": days_portfolio_ahead,
            "total_days_compared": total_days_compared,
        },
        counted_symbols=[c.__dict__ for c in counted],
        excluded_symbols=[e.__dict__ for e in excluded],
        caveats=caveats,
    )


def _zero_summary() -> dict:
    return {
        "portfolio_return_pct": 0.0,
        "benchmark_return_pct": 0.0,
        "alpha_pct": 0.0,
        "avg_daily_alpha_pp": 0.0,
        "days_portfolio_ahead": 0,
        "total_days_compared": 0,
    }
