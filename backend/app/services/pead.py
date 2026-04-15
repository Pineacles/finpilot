"""PEAD (Post-Earnings Announcement Drift) screener service.

Computes a 0-100 composite score measuring how strong a PEAD candidate a stock is,
based on EPS beat rate, surprise magnitude, and consistency.
In-memory cache with 6-hour TTL.
"""
import time
import logging
from datetime import datetime, timezone, timedelta
from statistics import stdev, mean

logger = logging.getLogger(__name__)

# In-memory cache: symbol -> (result_dict, timestamp)
_cache: dict = {}
CACHE_TTL = 6 * 3600  # 6 hours


def score_pead(symbol: str) -> dict:
    """Compute PEAD score for a symbol.

    Returns dict with:
      symbol, beat_streak, beat_rate, last_surprise_pct, avg_surprise_pct,
      next_earnings_date, days_to_earnings, pead_score, direction, computed_at

    On failure: {symbol, error: "no_earnings_data"}
    """
    sym = symbol.upper()

    # Cache check
    if sym in _cache:
        result, ts = _cache[sym]
        if time.time() - ts < CACHE_TTL:
            return result

    try:
        import yfinance as yf
        ticker = yf.Ticker(sym)
        ed = ticker.earnings_dates
    except Exception as exc:
        logger.warning("yfinance error for %s: %s", sym, exc)
        return {"symbol": sym, "error": "no_earnings_data"}

    if ed is None or ed.empty:
        return {"symbol": sym, "error": "no_earnings_data"}

    try:
        result = _compute(sym, ed)
    except Exception as exc:
        logger.warning("PEAD compute error for %s: %s", sym, exc)
        return {"symbol": sym, "error": "no_earnings_data"}

    _cache[sym] = (result, time.time())
    return result


def _compute(sym: str, ed) -> dict:
    import pandas as pd
    from datetime import date

    now = datetime.now(timezone.utc)
    today = now.date()

    # Normalise index to tz-aware datetimes
    if hasattr(ed.index, "tz") and ed.index.tz is None:
        ed.index = ed.index.tz_localize("UTC")

    # Split past vs future
    past = ed[ed.index <= pd.Timestamp(now)]
    future = ed[ed.index > pd.Timestamp(now)]

    # Identify columns — yfinance returns: 'EPS Estimate', 'Reported EPS', 'Surprise(%)'
    surprise_col = None
    for col in ed.columns:
        if "surprise" in col.lower():
            surprise_col = col
            break

    eps_estimate_col = None
    eps_actual_col = None
    for col in ed.columns:
        cl = col.lower()
        if "estimate" in cl:
            eps_estimate_col = col
        if "reported" in cl or "actual" in cl:
            eps_actual_col = col

    # Build list of (date, surprise_pct, beat) for past quarters
    records = []
    for idx, row in past.sort_index(ascending=False).iterrows():
        surprise_pct = None

        if surprise_col and not _isnan(row.get(surprise_col)):
            surprise_pct = float(row[surprise_col])
        elif eps_estimate_col and eps_actual_col:
            est = row.get(eps_estimate_col)
            act = row.get(eps_actual_col)
            if not _isnan(est) and not _isnan(act) and float(est) != 0:
                surprise_pct = (float(act) - float(est)) / abs(float(est)) * 100

        if surprise_pct is None:
            continue

        records.append({
            "date": idx.date() if hasattr(idx, "date") else idx,
            "surprise_pct": surprise_pct,
            "beat": surprise_pct > 0,
        })

    if not records:
        return {"symbol": sym, "error": "no_earnings_data"}

    # Use last 8 quarters
    last8 = records[:8]

    beat_streak = 0
    for r in records:
        if r["beat"]:
            beat_streak += 1
        else:
            break

    beat_rate = sum(1 for r in last8 if r["beat"]) / len(last8) * 100
    last_surprise_pct = records[0]["surprise_pct"]
    surprises = [r["surprise_pct"] for r in last8]
    avg_surprise_pct = mean(surprises)

    # Consistency: 1 - stdev/|avg| (clamped 0..1)
    if len(surprises) >= 2 and avg_surprise_pct != 0:
        consistency = max(0.0, min(1.0, 1 - stdev(surprises) / abs(avg_surprise_pct)))
    else:
        consistency = 0.5

    # Composite score (0-100)
    beat_rate_component = (beat_rate / 100) * 0.4 * 100
    surprise_component = min(abs(last_surprise_pct), 50) / 50 * 0.3 * 100
    consistency_component = consistency * 0.3 * 100
    pead_score = round(beat_rate_component + surprise_component + consistency_component, 1)
    pead_score = max(0.0, min(100.0, pead_score))

    # Direction
    if last_surprise_pct > 0:
        direction = "long"
    elif last_surprise_pct < 0:
        direction = "short"
    else:
        direction = "neutral"

    # Next earnings date
    next_earnings_date = None
    days_to_earnings = None
    if not future.empty:
        next_ts = future.sort_index().index[0]
        next_date = next_ts.date() if hasattr(next_ts, "date") else next_ts
        next_earnings_date = next_date.isoformat()
        days_to_earnings = (next_date - today).days

    return {
        "symbol": sym,
        "beat_streak": beat_streak,
        "beat_rate": round(beat_rate, 1),
        "last_surprise_pct": round(last_surprise_pct, 2),
        "avg_surprise_pct": round(avg_surprise_pct, 2),
        "next_earnings_date": next_earnings_date,
        "days_to_earnings": days_to_earnings,
        "pead_score": pead_score,
        "direction": direction,
        "quarters_used": len(last8),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _isnan(val) -> bool:
    if val is None:
        return True
    try:
        import math
        return math.isnan(float(val))
    except (TypeError, ValueError):
        return True
