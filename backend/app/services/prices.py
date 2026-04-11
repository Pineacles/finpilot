"""Free stock price service via Yahoo Finance.

No API key needed. Supports stocks, ETFs, crypto, indices.
"""
import time
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# In-memory cache: ticker -> {data, fetched_at}
_price_cache: dict[str, dict] = {}
CACHE_TTL = 30  # 30 seconds — frequent enough for live feel without hammering Yahoo


async def get_quote(ticker: str, cache_ttl: int | None = None) -> dict | None:
    """Get current price + metadata for a ticker. Optional cache_ttl override."""
    now = time.time()
    ttl = cache_ttl if cache_ttl is not None else CACHE_TTL
    cached = _price_cache.get(ticker)
    if cached and now - cached["fetched_at"] < ttl:
        return cached["data"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE}/{ticker}",
                params={"interval": "1d", "range": "5d"},
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                logger.warning(f"Yahoo quote failed for {ticker}: {resp.status_code}")
                return cached["data"] if cached else None

            result = resp.json()["chart"]["result"][0]
            meta = result["meta"]

            data = {
                "ticker": ticker,
                "price": meta["regularMarketPrice"],
                "prev_close": meta.get("chartPreviousClose", meta.get("previousClose", 0)),
                "currency": meta["currency"],
                "name": meta.get("shortName", ticker),
                "exchange": meta.get("exchangeName", ""),
                "market_state": meta.get("marketState", ""),
            }
            data["change"] = data["price"] - data["prev_close"]
            data["change_pct"] = (data["change"] / data["prev_close"] * 100) if data["prev_close"] else 0

            _price_cache[ticker] = {"data": data, "fetched_at": now}
            return data

    except Exception as e:
        logger.error(f"Yahoo quote error for {ticker}: {e}")
        return cached["data"] if cached else None


async def get_quotes_batch(tickers: list[str], cache_ttl: int | None = None) -> dict[str, dict]:
    """Get quotes for multiple tickers. Returns ticker -> quote dict."""
    results = {}
    for t in tickers:
        q = await get_quote(t, cache_ttl=cache_ttl)
        if q:
            results[t] = q
    return results


# FX rate cache
_fx_cache: dict[str, dict] = {}
FX_CACHE_TTL = 300  # 5 minutes


async def get_fx_rate(from_ccy: str, to_ccy: str) -> float:
    """Get exchange rate. Returns multiplier to convert from_ccy to to_ccy."""
    if from_ccy == to_ccy:
        return 1.0

    pair = f"{from_ccy}{to_ccy}=X"
    now = time.time()
    cached = _fx_cache.get(pair)
    if cached and now - cached["fetched_at"] < FX_CACHE_TTL:
        return cached["rate"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE}/{pair}",
                params={"interval": "1d", "range": "1d"},
                headers=_HEADERS,
            )
            if resp.status_code == 200:
                rate = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
                _fx_cache[pair] = {"rate": rate, "fetched_at": now}
                return rate
    except Exception as e:
        logger.warning(f"FX rate fetch failed for {pair}: {e}")

    # Fallback: try reverse
    reverse_pair = f"{to_ccy}{from_ccy}=X"
    cached = _fx_cache.get(reverse_pair)
    if cached:
        return 1.0 / cached["rate"]

    return 1.0  # Last resort


async def get_history(ticker: str, range: str = "1y", interval: str = "1d") -> list[dict]:
    """Get historical prices.

    range: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
    interval: 1m, 5m, 15m, 1d, 1wk, 1mo
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/{ticker}",
                params={"interval": interval, "range": range},
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                return []

            result = resp.json()["chart"]["result"][0]
            timestamps = result.get("timestamp", [])
            quotes = result["indicators"]["quote"][0]
            closes = quotes.get("close", [])

            # Use richer date format for intraday intervals so multiple points per day are distinct
            is_intraday = interval.endswith("m") and not interval.endswith("mo") or interval.endswith("h")
            fmt = "%Y-%m-%d %H:%M" if is_intraday else "%Y-%m-%d"
            history = []
            for i, ts in enumerate(timestamps):
                if i < len(closes) and closes[i] is not None:
                    history.append({
                        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
                        "close": round(closes[i], 2),
                    })
            return history

    except Exception as e:
        logger.error(f"Yahoo history error for {ticker}: {e}")
        return []
