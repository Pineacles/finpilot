"""Quantitative risk analytics — CVaR, Half-Kelly, Macro Regime, Black Swan.

All CPU-only, no paid data sources. Uses yfinance via the existing prices service.
In-memory caching with TTL to avoid hammering Yahoo Finance.
"""
import logging
import time
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)

# ── In-memory caches ──────────────────────────────────────────────

_history_cache: dict[str, dict] = {}   # symbol -> {closes, fetched_at}
_macro_cache: dict = {}                  # single entry {data, fetched_at}
HISTORY_TTL = 600   # 10 min — price history doesn't change minute-to-minute
MACRO_TTL = 3600    # 1 hour — regime detection


# ── Price-history helper ─────────────────────────────────────────

async def _get_closes(symbol: str, days: int = 365) -> list[float]:
    """Return a list of daily closing prices, most-recent-last.
    Uses the existing prices.get_history helper and caches results.
    """
    from app.services.prices import get_history

    cache_key = f"{symbol}:{days}"
    now = time.time()
    cached = _history_cache.get(cache_key)
    if cached and now - cached["fetched_at"] < HISTORY_TTL:
        return cached["closes"]

    yf_range = "1y" if days <= 252 else "2y"
    hist = await get_history(symbol, range=yf_range, interval="1d")
    if not hist:
        return []

    closes = [h["close"] for h in hist if h["close"] is not None]
    # Trim to requested days
    closes = closes[-days:] if len(closes) > days else closes

    _history_cache[cache_key] = {"closes": closes, "fetched_at": now}
    return closes


def _daily_returns(closes: list[float]) -> np.ndarray:
    """Convert a price series to daily log-returns."""
    arr = np.array(closes, dtype=float)
    if len(arr) < 2:
        return np.array([])
    return np.diff(arr) / arr[:-1]


# ── 1. CVaR / Expected Shortfall ────────────────────────────────

async def compute_cvar(
    positions: list[dict],  # [{symbol, market_value_chf, currency}]
    total_value_chf: float,
    lookback_days: int = 252,
) -> dict:
    """Compute historical CVaR (95% and 99%) for a portfolio.

    Returns CHF-denominated expected loss figures. Negative = loss.
    positions: list of dicts with keys: symbol, market_value_chf
    """
    if not positions or total_value_chf <= 0:
        return {"error": "no_positions"}

    from app.services.prices import get_fx_rate

    # Build weighted portfolio daily P&L series
    all_returns: list[np.ndarray] = []
    weights: list[float] = []

    for pos in positions:
        sym = pos["symbol"]
        closes = await _get_closes(sym, lookback_days + 5)
        if len(closes) < 30:
            logger.warning(f"CVaR: insufficient history for {sym} ({len(closes)} days)")
            continue
        rets = _daily_returns(closes)
        if len(rets) == 0:
            continue
        all_returns.append(rets)
        weights.append(pos["market_value_chf"] / total_value_chf)

    if not all_returns:
        return {"error": "insufficient_history"}

    # Align to shortest series
    min_len = min(len(r) for r in all_returns)
    min_len = min(min_len, lookback_days)
    aligned = np.column_stack([r[-min_len:] for r in all_returns])
    w = np.array(weights[:len(all_returns)])
    w = w / w.sum()  # re-normalize in case some symbols had no data

    # Portfolio daily returns (weighted sum)
    port_returns = aligned @ w
    port_pnl = port_returns * total_value_chf  # CHF P&L per day

    # VaR and CVaR at 95% and 99%
    var_95 = float(np.percentile(port_pnl, 5))
    var_99 = float(np.percentile(port_pnl, 1))
    cvar_95 = float(np.mean(port_pnl[port_pnl <= var_95]))
    cvar_99 = float(np.mean(port_pnl[port_pnl <= var_99]))

    return {
        "cvar_95": round(cvar_95, 2),
        "cvar_99": round(cvar_99, 2),
        "var_95": round(var_95, 2),
        "var_99": round(var_99, 2),
        "lookback_days": lookback_days,
        "sample_size": int(min_len),
        "total_portfolio_chf": round(total_value_chf, 2),
        "cvar_95_pct": round(abs(cvar_95) / total_value_chf * 100, 3) if total_value_chf else 0,
        "cvar_99_pct": round(abs(cvar_99) / total_value_chf * 100, 3) if total_value_chf else 0,
    }


# ── 2. Half-Kelly position sizing ───────────────────────────────

async def compute_kelly(
    symbol: str,
    expected_return_pct: float,
    conviction: float,
    portfolio_value_chf: float,
    lookback_days: int = 60,
) -> dict:
    """Half-Kelly position size for a single-asset candidate trade.

    Kelly = μ / σ²  (single-asset, no-debt simplification)
    Half-Kelly = 0.5 × Kelly × conviction, clamped to [0, 0.20]
    """
    closes = await _get_closes(symbol, lookback_days + 5)
    if len(closes) < 20:
        return {"error": "insufficient_history", "available_days": len(closes)}

    rets = _daily_returns(closes)
    if len(rets) == 0:
        return {"error": "insufficient_history", "available_days": 0}

    # Annualised volatility
    sigma_daily = float(np.std(rets, ddof=1))
    sigma_annual = sigma_daily * np.sqrt(252)
    sigma2_annual = sigma_annual ** 2

    if sigma2_annual < 1e-10:
        return {"error": "zero_variance"}

    mu = expected_return_pct / 100.0
    kelly_raw = mu / sigma2_annual
    half_kelly = 0.5 * kelly_raw * conviction
    half_kelly_clamped = float(np.clip(half_kelly, 0.0, 0.20))

    suggested_chf = half_kelly_clamped * portfolio_value_chf

    # Approximate share count (need current price)
    from app.services.prices import get_quote
    quote = await get_quote(symbol)
    if quote and quote.get("price") and quote.get("currency"):
        from app.services.prices import get_fx_rate
        fx = await get_fx_rate(quote["currency"], "CHF") if quote["currency"] != "CHF" else 1.0
        price_chf = quote["price"] * fx
        suggested_shares = int(suggested_chf / price_chf) if price_chf > 0 else 0
        current_price = round(quote["price"], 4)
        current_price_chf = round(price_chf, 4)
    else:
        suggested_shares = 0
        current_price = None
        current_price_chf = None

    return {
        "symbol": symbol,
        "kelly_fraction": round(kelly_raw, 5),
        "half_kelly_fraction": round(half_kelly_clamped, 5),
        "suggested_chf": round(suggested_chf, 2),
        "suggested_shares": suggested_shares,
        "volatility_60d": round(sigma_annual * 100, 2),  # annualised, in %
        "max_position_pct": 0.20,
        "expected_return_pct": expected_return_pct,
        "conviction": conviction,
        "current_price": current_price,
        "current_price_chf": current_price_chf,
        "lookback_days": lookback_days,
    }


# ── 3. Macro Regime Detection ───────────────────────────────────

SECTOR_TILTS = {
    "Expansionary": ["Information Technology", "Consumer Discretionary"],
    "Late-Cycle": ["Energy", "Materials", "Industrials"],
    "Contractionary": ["Utilities", "Healthcare", "Consumer Staples"],
    "Recovery": ["Financials", "Real Estate", "Small-Caps"],
}


async def compute_macro_regime() -> dict:
    """Classify current macro regime from yield-curve spread + VIX.

    Uses: ^TNX (10Y Treasury), ^IRX (3M Treasury, proxy for short-end),
           ^VIX (CBOE Volatility Index).

    Returns cached result for MACRO_TTL seconds.
    """
    now = time.time()
    if _macro_cache and now - _macro_cache.get("fetched_at", 0) < MACRO_TTL:
        return _macro_cache["data"]

    from app.services.prices import get_quote

    # Fetch indicators
    tnx = await get_quote("^TNX")   # 10Y yield (%)
    irx = await get_quote("^IRX")   # 3M yield (%)
    vix = await get_quote("^VIX")   # VIX index

    tnx_val = tnx["price"] if tnx else None
    irx_val = irx["price"] if irx else None
    vix_val = vix["price"] if vix else None

    # Yield curve: 10Y − 3M, in basis points
    yield_curve_bps: float | None = None
    if tnx_val is not None and irx_val is not None:
        yield_curve_bps = round((tnx_val - irx_val) * 100, 1)  # % → bps

    # VIX z-score over 60d rolling window
    vix_zscore: float | None = None
    vix_closes = await _get_closes("^VIX", 65)
    if len(vix_closes) >= 10:
        vix_arr = np.array(vix_closes[-60:], dtype=float)
        mu_vix = float(np.mean(vix_arr))
        sigma_vix = float(np.std(vix_arr, ddof=1))
        if sigma_vix > 0 and vix_val is not None:
            vix_zscore = round((vix_val - mu_vix) / sigma_vix, 3)

    # Detect "steepening from inversion" by comparing last 10d of yield curve
    steepening = False
    tnx_closes = await _get_closes("^TNX", 20)
    irx_closes = await _get_closes("^IRX", 20)
    if len(tnx_closes) >= 10 and len(irx_closes) >= 10:
        n = min(len(tnx_closes), len(irx_closes))
        spreads = np.array(tnx_closes[-n:]) - np.array(irx_closes[-n:])
        # Recovery: was inverted recently AND now steepening
        if spreads[0] < 0 and spreads[-1] > spreads[0]:
            steepening = True

    # Classify regime
    regime = "Unknown"
    confidence = 0.5

    if yield_curve_bps is not None and vix_val is not None:
        if steepening and yield_curve_bps < 100:
            regime = "Recovery"
            confidence = 0.65
        elif yield_curve_bps < 0 and vix_val > 25:
            regime = "Contractionary"
            confidence = 0.85
        elif yield_curve_bps < 0 or vix_val > 25:
            regime = "Contractionary"
            confidence = 0.7
        elif yield_curve_bps < 50 or (18 <= vix_val <= 25):
            regime = "Late-Cycle"
            confidence = 0.75
        elif yield_curve_bps >= 50 and vix_val < 18:
            regime = "Expansionary"
            confidence = 0.8
        else:
            regime = "Late-Cycle"
            confidence = 0.55

    result = {
        "regime": regime,
        "indicators": {
            "yield_curve_bps": yield_curve_bps,
            "tnx_pct": round(tnx_val, 3) if tnx_val else None,
            "irx_pct": round(irx_val, 3) if irx_val else None,
            "vix": round(vix_val, 2) if vix_val else None,
            "vix_zscore_60d": vix_zscore,
        },
        "sector_tilts": SECTOR_TILTS.get(regime, []),
        "confidence": confidence,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "note": "Yield curve: ^TNX (10Y) − ^IRX (3M Treasury) as short-end proxy",
    }

    _macro_cache["data"] = result
    _macro_cache["fetched_at"] = now
    return result


# ── 4. Black Swan Detection ──────────────────────────────────────

async def compute_black_swan(
    positions: list[dict],  # [{symbol, market_value_chf}]
    total_value_chf: float,
    lookback_days: int = 252,
) -> dict:
    """Detect black-swan conditions.

    Triggers: VIX z-score (60d) > 3, CVaR_95 > 8% of portfolio,
              OR any holding's daily return z-score (60d) < -4.
    """
    reasons = []

    # 1. VIX z-score
    vix_closes = await _get_closes("^VIX", 65)
    from app.services.prices import get_quote
    vix_q = await get_quote("^VIX")
    vix_val = vix_q["price"] if vix_q else None

    if len(vix_closes) >= 10 and vix_val is not None:
        arr = np.array(vix_closes[-60:], dtype=float)
        mu, sigma = float(np.mean(arr)), float(np.std(arr, ddof=1))
        if sigma > 0:
            z = (vix_val - mu) / sigma
            if z > 3:
                reasons.append({
                    "type": "vix_zscore",
                    "value": round(z, 3),
                    "threshold": 3.0,
                    "description": f"VIX z-score {z:.2f} > 3 (VIX={vix_val:.1f})",
                })

    # 2. CVaR_95 > 8% of portfolio
    if positions and total_value_chf > 0:
        cvar_result = await compute_cvar(positions, total_value_chf, lookback_days)
        if "cvar_95_pct" in cvar_result:
            cvar_pct = cvar_result["cvar_95_pct"]
            if cvar_pct > 8.0:
                reasons.append({
                    "type": "cvar_95",
                    "value": round(cvar_pct, 3),
                    "threshold": 8.0,
                    "description": f"CVaR 95% is {cvar_pct:.1f}% of portfolio (>{8}%)",
                })

        # 3. Individual holding z-scores
        for pos in positions:
            sym = pos["symbol"]
            closes = await _get_closes(sym, 65)
            if len(closes) < 10:
                continue
            rets = _daily_returns(closes[-60:])
            if len(rets) < 5:
                continue
            last_ret = rets[-1] if len(rets) > 0 else None
            if last_ret is None:
                continue
            mu_r = float(np.mean(rets))
            sigma_r = float(np.std(rets, ddof=1))
            if sigma_r > 0:
                z_r = (last_ret - mu_r) / sigma_r
                if z_r < -4:
                    reasons.append({
                        "type": "holding_return_zscore",
                        "symbol": sym,
                        "value": round(z_r, 3),
                        "threshold": -4.0,
                        "description": f"{sym} daily return z-score {z_r:.2f} < -4",
                    })

    active = len(reasons) > 0
    severity = "info"
    if active:
        if len(reasons) >= 2 or any(r["type"] == "cvar_95" for r in reasons):
            severity = "critical"
        else:
            severity = "warn"

    return {
        "active": active,
        "severity": severity,
        "reasons": reasons,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
