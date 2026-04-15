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


# ── 5. PCA Factor Model ──────────────────────────────────────────

_pca_cache: dict = {}
PCA_TTL = 3600  # 1 hour


async def compute_pca(
    positions: list[dict],  # [{symbol}]
    lookback_days: int = 252,
) -> dict:
    """Run PCA on portfolio returns matrix.

    Returns top-5 factors with variance explained, loadings, and
    concentration risk metrics. Drops holdings with insufficient history.
    """
    if not positions:
        return {"error": "no_positions"}

    cache_key = "pca:" + ",".join(sorted(p["symbol"] for p in positions))
    now = time.time()
    cached = _pca_cache.get(cache_key)
    if cached and now - cached["fetched_at"] < PCA_TTL:
        return cached["data"]

    from sklearn.decomposition import PCA
    import numpy as np

    returns_map: dict[str, np.ndarray] = {}
    for pos in positions:
        sym = pos["symbol"]
        closes = await _get_closes(sym, lookback_days + 5)
        if len(closes) < 30:
            logger.warning(f"PCA: skipping {sym} — only {len(closes)} days")
            continue
        rets = _daily_returns(closes)
        if len(rets) >= 30:
            returns_map[sym] = rets

    if len(returns_map) < 2:
        return {"error": "insufficient_holdings"}

    symbols = list(returns_map.keys())
    min_len = min(len(r) for r in returns_map.values())
    min_len = min(min_len, lookback_days)
    matrix = np.column_stack([returns_map[s][-min_len:] for s in symbols])

    # Standardise (PCA on correlation structure)
    mu = matrix.mean(axis=0)
    sigma = matrix.std(axis=0, ddof=1)
    sigma[sigma < 1e-12] = 1.0
    X = (matrix - mu) / sigma

    n_components = min(5, len(symbols))
    pca = PCA(n_components=n_components)
    pca.fit(X)

    factors = []
    for idx in range(n_components):
        loadings = [
            {"symbol": sym, "loading": round(float(pca.components_[idx, j]), 4)}
            for j, sym in enumerate(symbols)
        ]
        loadings.sort(key=lambda x: abs(x["loading"]), reverse=True)

        var_pct = round(float(pca.explained_variance_ratio_[idx]) * 100, 2)

        # Simple interpretation heuristic
        signs = [l["loading"] for l in loadings]
        interpretation = None
        if idx == 0:
            if all(s > 0 for s in signs) or all(s < 0 for s in signs):
                interpretation = "Market beta"
            else:
                interpretation = "Sector rotation"

        factors.append({
            "idx": idx,
            "variance_explained_pct": var_pct,
            "loadings": loadings,
            "interpretation": interpretation,
        })

    total_var = round(float(sum(pca.explained_variance_ratio_[:n_components])) * 100, 2)
    top_factor_pct = factors[0]["variance_explained_pct"]
    var_ratios = [f["variance_explained_pct"] / 100 for f in factors]
    herfindahl = round(float(sum(v ** 2 for v in var_ratios)), 4)

    result = {
        "factors": factors,
        "total_variance_explained_pct": total_var,
        "concentration_risk": {
            "top_factor_pct": top_factor_pct,
            "herfindahl_index": herfindahl,
        },
        "sample_size": int(min_len),
        "holdings_used": symbols,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    _pca_cache[cache_key] = {"data": result, "fetched_at": now}
    return result


# ── 6. Cointegration Pairs ───────────────────────────────────────

_coint_cache: dict = {}
COINT_TTL = 3600  # 1 hour

SMI_UNIVERSE = [
    "NESN.SW", "ROG.SW", "NOVN.SW", "UBSG.SW", "ZURN.SW",
    "ABBN.SW", "CFR.SW", "GIVN.SW", "SREN.SW", "HOLN.SW",
]


async def compute_cointegration(
    symbols: list[str] | None = None,
    lookback_days: int = 252,
) -> dict:
    """Engle-Granger cointegration test on all pairs in the universe.

    Returns pairs with p-value < 0.05, sorted by |spread_zscore|.
    """
    if symbols is None or len(symbols) == 0:
        symbols = SMI_UNIVERSE

    symbols = [s.upper() for s in symbols]
    cache_key = "coint:" + ",".join(sorted(symbols))
    now = time.time()
    cached = _coint_cache.get(cache_key)
    if cached and now - cached["fetched_at"] < COINT_TTL:
        return cached["data"]

    from statsmodels.tsa.stattools import coint
    import numpy as np

    # Fetch log-prices
    log_prices: dict[str, np.ndarray] = {}
    for sym in symbols:
        closes = await _get_closes(sym, lookback_days + 5)
        if len(closes) >= 60:
            arr = np.array(closes[-lookback_days:], dtype=float)
            log_prices[sym] = np.log(arr)
        else:
            logger.warning(f"Coint: skipping {sym} — only {len(closes)} days")

    valid_syms = list(log_prices.keys())
    if len(valid_syms) < 2:
        return {"pairs": [], "universe": symbols, "sample_size": lookback_days,
                "computed_at": datetime.now(timezone.utc).isoformat()}

    pairs = []
    for i in range(len(valid_syms)):
        for j in range(i + 1, len(valid_syms)):
            sym_a, sym_b = valid_syms[i], valid_syms[j]
            lp_a = log_prices[sym_a]
            lp_b = log_prices[sym_b]
            min_len = min(len(lp_a), len(lp_b))
            lp_a = lp_a[-min_len:]
            lp_b = lp_b[-min_len:]

            try:
                score, p_value, _ = coint(lp_a, lp_b)
            except Exception as e:
                logger.warning(f"Coint {sym_a}/{sym_b} failed: {e}")
                continue

            if p_value >= 0.05:
                continue

            # OLS hedge ratio: regress lp_b on lp_a
            try:
                coeffs = np.polyfit(lp_a, lp_b, 1)
                hedge_ratio = float(coeffs[0])
            except Exception:
                hedge_ratio = 1.0

            spread = lp_b - hedge_ratio * lp_a

            # Rolling 60d z-score (use last 60 days of spread)
            window = min(60, len(spread))
            spread_window = spread[-window:]
            mu_s = float(np.mean(spread_window))
            std_s = float(np.std(spread_window, ddof=1))
            current_spread = float(spread[-1])
            spread_zscore = round((current_spread - mu_s) / std_s, 3) if std_s > 1e-12 else 0.0

            # OU half-life: AR(1) on spread diff
            try:
                from statsmodels.regression.linear_model import OLS
                from statsmodels.tools import add_constant
                spread_lag = spread[:-1]
                spread_diff = np.diff(spread)
                X_ar = add_constant(spread_lag)
                ar_fit = OLS(spread_diff, X_ar).fit()
                phi = float(ar_fit.params[1])
                if phi < 0:
                    half_life = round(-np.log(2) / np.log(1 + phi), 1)
                else:
                    half_life = None
            except Exception:
                half_life = None

            # Trading signal
            if abs(spread_zscore) > 2:
                signal = "long_a_short_b" if spread_zscore > 0 else "short_a_long_b"
            else:
                signal = "neutral"

            # 252d correlation
            ret_a = np.diff(lp_a)
            ret_b = np.diff(lp_b)
            corr = round(float(np.corrcoef(ret_a, ret_b)[0, 1]), 4)

            pairs.append({
                "a": sym_a,
                "b": sym_b,
                "p_value": round(float(p_value), 5),
                "hedge_ratio": round(hedge_ratio, 4),
                "current_spread": round(current_spread, 6),
                "spread_zscore": spread_zscore,
                "half_life_days": half_life,
                "signal": signal,
                "last_252d_corr": corr,
            })

    # Sort by |zscore| desc, limit 20
    pairs.sort(key=lambda x: abs(x["spread_zscore"]), reverse=True)
    pairs = pairs[:20]

    result = {
        "pairs": pairs,
        "universe": valid_syms,
        "sample_size": lookback_days,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    _coint_cache[cache_key] = {"data": result, "fetched_at": now}
    return result


async def get_spread_history(
    sym_a: str,
    sym_b: str,
    hedge_ratio: float,
    days: int = 90,
) -> list[dict]:
    """Return last `days` of spread + ±2σ bands for chart rendering."""
    closes_a = await _get_closes(sym_a, days + 5)
    closes_b = await _get_closes(sym_b, days + 5)
    min_len = min(len(closes_a), len(closes_b), days)
    if min_len < 10:
        return []

    import numpy as np
    lp_a = np.log(np.array(closes_a[-min_len:], dtype=float))
    lp_b = np.log(np.array(closes_b[-min_len:], dtype=float))
    spread = lp_b - hedge_ratio * lp_a

    mu = float(np.mean(spread))
    std = float(np.std(spread, ddof=1))

    # Approximate dates (trading days back from today)
    from datetime import date, timedelta
    today = date.today()
    bdays: list[date] = []
    d = today
    while len(bdays) < min_len:
        if d.weekday() < 5:
            bdays.append(d)
        d -= timedelta(days=1)
    bdays = list(reversed(bdays))

    return [
        {
            "date": bdays[i].isoformat(),
            "spread": round(float(spread[i]), 6),
            "upper": round(mu + 2 * std, 6),
            "lower": round(mu - 2 * std, 6),
        }
        for i in range(min_len)
    ]
