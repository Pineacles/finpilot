"""Insider activity classifier service.

Classifies recent insider transactions into:
  cluster_buying | c_suite_disposition | routine_option_exercise |
  contrarian_accumulation | noise

In-memory cache with 12-hour TTL.
"""
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# In-memory cache: (symbol, days) -> (result_dict, timestamp)
_cache: dict = {}
CACHE_TTL = 12 * 3600  # 12 hours

# Titles considered C-suite
_CSUITE_TITLES = {
    "chief executive officer", "ceo",
    "chief financial officer", "cfo",
    "chief operating officer", "coo",
    "president",
}

_DIRECTOR_KEYWORDS = {"director", "board", "trustee", "chairman", "chair"}


def classify_insider_activity(symbol: str, days: int = 90) -> dict:
    """Classify insider transactions for `symbol` over last `days` days.

    Returns aggregated classification dict or {symbol, error: "no_insider_data"}.
    """
    sym = symbol.upper()
    cache_key = (sym, days)

    if cache_key in _cache:
        result, ts = _cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            return result

    try:
        import yfinance as yf
        ticker = yf.Ticker(sym)
        txns_df = ticker.insider_transactions
    except Exception as exc:
        logger.warning("yfinance error for %s insider: %s", sym, exc)
        return {"symbol": sym, "error": "no_insider_data"}

    if txns_df is None or txns_df.empty:
        return {"symbol": sym, "error": "no_insider_data"}

    try:
        result = _classify(sym, txns_df, days)
    except Exception as exc:
        logger.warning("Insider classify error for %s: %s", sym, exc)
        return {"symbol": sym, "error": "no_insider_data"}

    _cache[cache_key] = (result, time.time())
    return result


def _classify(sym: str, df, days: int) -> dict:
    import pandas as pd

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Normalise date column — yfinance insider_transactions uses 'Start Date'
    date_col = None
    for col in df.columns:
        if col.lower() in ("start date", "date"):
            date_col = col
            break
    if date_col is None:
        for col in df.columns:
            if "date" in col.lower() or "start" in col.lower():
                date_col = col
                break
    if date_col is None:
        # Try index
        df = df.reset_index()
        for col in df.columns:
            if "date" in col.lower():
                date_col = col
                break

    if date_col is None:
        df["_date"] = pd.to_datetime(df.index, utc=True, errors="coerce")
        date_col = "_date"
    else:
        df["_date"] = pd.to_datetime(df[date_col], utc=True, errors="coerce")

    df = df.dropna(subset=["_date"])

    df = df[df["_date"] >= pd.Timestamp(cutoff)]

    if df.empty:
        return {"symbol": sym, "error": "no_insider_data"}

    # Identify columns
    # yfinance insider_transactions columns: Insider, Position, Transaction, Shares, Value
    name_col = _find_col(df, ["insider", "name"])
    title_col = _find_col(df, ["position", "title", "relationship"])
    txn_col = _find_col(df, ["transaction", "text", "type"])
    shares_col = _find_col(df, ["shares"])
    value_col = _find_col(df, ["value"])

    # Get 52-week low for contrarian check
    low_52w = _get_52w_low(sym)
    current_price = _get_current_price(sym)

    # Build normalised transaction list
    transactions = []
    for _, row in df.sort_values("_date").iterrows():
        name = str(row[name_col]).strip() if name_col else "Unknown"
        title = str(row[title_col]).strip() if title_col else ""
        txn_type_raw = str(row[txn_col]).strip() if txn_col else ""
        shares = _safe_float(row[shares_col]) if shares_col else 0.0
        value = _safe_float(row[value_col]) if value_col else 0.0
        dt = row["_date"]

        action = _parse_action(txn_type_raw)
        transactions.append({
            "name": name,
            "title": title,
            "title_lower": title.lower(),
            "action": action,
            "txn_type_raw": txn_type_raw,
            "shares": shares,
            "value": value,
            "date": dt,
        })

    # Classify each transaction
    classified = []
    for t in transactions:
        cls = _classify_txn(t, transactions, low_52w, current_price)
        classified.append({**t, "classification": cls})

    # Aggregate counts
    counts = {
        "cluster_buying": 0,
        "c_suite_disposition": 0,
        "routine_option_exercise": 0,
        "contrarian_accumulation": 0,
        "noise": 0,
    }
    for c in classified:
        counts[c["classification"]] += 1

    # Net shares / value
    net_shares = sum(
        c["shares"] if c["action"] == "buy" else -c["shares"]
        for c in classified
    )
    net_value = sum(
        c["value"] if c["action"] == "buy" else -c["value"]
        for c in classified
    )

    # Top 5 signals (non-noise first, then sorted by |value|)
    signal_txns = sorted(
        [c for c in classified if c["classification"] != "noise"],
        key=lambda x: abs(x.get("value", 0)),
        reverse=True,
    )[:5]
    if len(signal_txns) < 5:
        signal_txns += sorted(
            [c for c in classified if c["classification"] == "noise"],
            key=lambda x: abs(x.get("value", 0)),
            reverse=True,
        )[: 5 - len(signal_txns)]

    top_signals = [
        {
            "type": c["classification"],
            "insider_name": c["name"],
            "title": c["title"],
            "date": c["date"].isoformat() if hasattr(c["date"], "isoformat") else str(c["date"]),
            "shares": c["shares"],
            "value": c["value"],
            "action": c["action"],
        }
        for c in signal_txns
    ]

    # Signal strength & direction
    strength, direction = _signal_strength_direction(counts, net_shares)

    return {
        "symbol": sym,
        "window_days": days,
        "transactions_count": len(classified),
        "classifications": counts,
        "net_shares_bought": int(net_shares),
        "net_value_chf": round(net_value, 2),
        "signal_strength": strength,
        "signal_direction": direction,
        "top_signals": top_signals,
        "computed_at": now.isoformat(),
    }


def _classify_txn(t: dict, all_txns: list, low_52w: float | None, current_price: float | None) -> str:
    """Classify a single transaction using heuristics."""
    action = t["action"]
    title_lower = t["title_lower"]
    value = t.get("value", 0) or 0
    date = t["date"]

    # Routine option exercise: BUY followed by SELL same/next day
    if action == "buy":
        for other in all_txns:
            if other is t:
                continue
            if other["action"] != "sell":
                continue
            try:
                delta = abs((other["date"] - date).total_seconds())
            except Exception:
                continue
            if delta <= 2 * 86400:  # within 2 days
                return "routine_option_exercise"

    if action == "sell":
        for other in all_txns:
            if other is t:
                continue
            if other["action"] != "buy":
                continue
            if other["name"] != t["name"]:
                continue
            try:
                delta = abs((other["date"] - date).total_seconds())
            except Exception:
                continue
            if delta <= 2 * 86400:
                return "routine_option_exercise"

    # C-suite disposition
    if action == "sell":
        title_tokens = set(title_lower.replace(",", " ").split())
        is_csuite = bool(title_tokens & _CSUITE_TITLES) or any(
            kw in title_lower for kw in _CSUITE_TITLES
        )
        if is_csuite and abs(value) > 500_000:
            return "c_suite_disposition"

    # Cluster buying: ≥2 different insiders BUY within 14 days
    if action == "buy":
        buyers_in_window = set()
        for other in all_txns:
            if other["action"] != "buy":
                continue
            try:
                delta = abs((other["date"] - date).total_seconds())
            except Exception:
                continue
            if delta <= 14 * 86400:
                buyers_in_window.add(other["name"])
        if len(buyers_in_window) >= 2:
            return "cluster_buying"

    # Contrarian accumulation: BUY by director near 52w low
    if action == "buy":
        is_director = any(kw in title_lower for kw in _DIRECTOR_KEYWORDS)
        if is_director and low_52w is not None and current_price is not None and current_price > 0:
            within_5pct = current_price <= low_52w * 1.05
            if within_5pct:
                return "contrarian_accumulation"

    return "noise"


def _signal_strength_direction(counts: dict, net_shares: float) -> tuple[str, str]:
    cb = counts["cluster_buying"]
    ca = counts["contrarian_accumulation"]
    csd = counts["c_suite_disposition"]
    roe = counts["routine_option_exercise"]
    noise = counts["noise"]

    if cb >= 3 or ca >= 2:
        return "very_high", "bullish"
    if cb >= 2:
        return "high", "bullish"
    if csd >= 1:
        return "high", "bearish"
    if cb >= 1 or ca >= 1:
        return "moderate", "bullish"
    if csd > 0:
        return "moderate", "bearish"
    if roe > 0:
        return "low", "neutral"
    return "none", "neutral"


def _parse_action(raw: str) -> str:
    rl = raw.lower()
    if any(k in rl for k in ("purchase", "buy", "acquisition", "acqui")):
        return "buy"
    if any(k in rl for k in ("sale", "sell", "sold", "disposition", "dispose")):
        return "sell"
    return "unknown"


def _find_col(df, keywords: list) -> str | None:
    for kw in keywords:
        for col in df.columns:
            if kw in col.lower():
                return col
    return None


def _safe_float(val) -> float:
    try:
        if val is None:
            return 0.0
        import math
        f = float(val)
        return 0.0 if math.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


def _get_current_price(sym: str) -> float | None:
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        info = t.fast_info
        return float(info.last_price)
    except Exception:
        return None


def _get_52w_low(sym: str) -> float | None:
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        hist = t.history(period="1y")
        if hist.empty:
            return None
        return float(hist["Low"].min())
    except Exception:
        return None
