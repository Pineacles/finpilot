"""Free stock price service via Yahoo Finance.

No API key needed. Supports stocks, ETFs, crypto, indices.
"""
import re
import time
import logging
from datetime import datetime, timezone

import httpx

from app.services.currency import normalize_price, normalize_currency

logger = logging.getLogger(__name__)

_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo symbols: letters, digits and . - ^ = (e.g. BRK-B, NESN.SW, ^GSPC,
# CHFEUR=X). Anything else (slashes, ?, #, %, whitespace) could redirect the
# request to another Yahoo path, so it is refused before a URL is built.
_TICKER_RE = re.compile(r"^[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,19}$")


def is_valid_ticker(ticker: str) -> bool:
    return isinstance(ticker, str) and bool(_TICKER_RE.fullmatch(ticker))

# In-memory cache: ticker -> {data, fetched_at}
_price_cache: dict[str, dict] = {}
CACHE_TTL = 30  # 30 seconds: frequent enough for live feel without hammering Yahoo


async def get_quote(ticker: str, cache_ttl: int | None = None) -> dict | None:
    """Get current price + metadata for a ticker. Optional cache_ttl override."""
    if not is_valid_ticker(ticker):
        logger.warning("Rejected invalid ticker format")
        return None
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
                if cached:
                    return {**cached["data"], "quote_fetch_failed": True}
                return None

            result = resp.json()["chart"]["result"][0]
            meta = result["meta"]

            raw_ccy = meta["currency"]
            raw_price = meta["regularMarketPrice"]
            raw_prev = meta.get("chartPreviousClose", meta.get("previousClose", 0))

            # Normalize subunit currencies (e.g. GBp pence -> GBP, divide price by 100)
            price, currency = normalize_price(raw_price, raw_ccy)
            prev_close, _ = normalize_price(raw_prev, raw_ccy)
            if raw_ccy != currency:
                logger.info(f"Normalized {ticker} currency {raw_ccy} -> {currency} (price {raw_price} -> {price})")

            data = {
                "ticker": ticker,
                "price": price,
                "prev_close": prev_close,
                "currency": currency,
                "name": meta.get("shortName", ticker),
                "exchange": meta.get("exchangeName", ""),
                "market_state": meta.get("marketState", ""),
            }
            data["change"] = data["price"] - data["prev_close"]
            data["change_pct"] = (data["change"] / data["prev_close"] * 100) if data["prev_close"] else 0
            # Fresh, successful fetch this request, not a stale fallback.
            data["quote_fetch_failed"] = False

            _price_cache[ticker] = {"data": data, "fetched_at": now}
            return data

    except Exception as e:
        logger.error(f"Yahoo quote error for {ticker}: {e}")
        if cached:
            # We have something to show, but be honest that *this request's*
            # live fetch failed: callers use this to decide staleness/warnings
            # instead of silently treating the cached value as fresh.
            return {**cached["data"], "quote_fetch_failed": True}
        return None


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


async def get_fx_rate(from_ccy: str, to_ccy: str) -> float | None:
    """Get exchange rate. Returns multiplier to convert from_ccy to to_ccy,
    or None if it could not be determined this request.

    IMPORTANT: this used to silently fall back to 1.0 on failure, which
    quietly corrupted CHF totals whenever Yahoo's FX endpoint hiccuped.
    Callers MUST treat None as "unknown": either use get_cached_fx_rate()
    for a best-effort stale value (and surface a warning that it's stale),
    or exclude the affected amount from CHF totals with a warning naming
    the affected symbol(s). Never substitute 1.0.

    Subunit codes (GBp, ZAC, etc.) are automatically promoted to their major
    currency before the FX lookup; callers need not pre-normalize.
    """
    # Normalize subunit codes up front: GBp -> GBP, etc.
    from_ccy, _ = normalize_currency(from_ccy)
    to_ccy, _ = normalize_currency(to_ccy)

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
            logger.warning(f"FX rate fetch failed for {pair}: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"FX rate fetch failed for {pair}: {e}")

    # Try a fresh live fetch of the reverse pair: some crosses are only
    # listed one direction on Yahoo. Still an honest, fresh computation.
    reverse_pair = f"{to_ccy}{from_ccy}=X"
    now = time.time()
    cached_rev = _fx_cache.get(reverse_pair)
    if cached_rev and now - cached_rev["fetched_at"] < FX_CACHE_TTL and cached_rev["rate"]:
        return 1.0 / cached_rev["rate"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE}/{reverse_pair}",
                params={"interval": "1d", "range": "1d"},
                headers=_HEADERS,
            )
            if resp.status_code == 200:
                rate = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
                _fx_cache[reverse_pair] = {"rate": rate, "fetched_at": now}
                return 1.0 / rate if rate else None
    except Exception as e:
        logger.warning(f"FX rate fetch failed for {reverse_pair}: {e}")

    return None


def get_cached_fx_rate(from_ccy: str, to_ccy: str) -> float | None:
    """Best-effort *stale* FX rate lookup, ignoring TTL: a fallback for when
    get_fx_rate() returns None. Returns None if this pair (or its reverse)
    has never been successfully fetched in this process's lifetime.

    Callers that use this MUST surface a warning that the rate may be stale;
    this function does not do that itself.
    """
    from_ccy, _ = normalize_currency(from_ccy)
    to_ccy, _ = normalize_currency(to_ccy)
    if from_ccy == to_ccy:
        return 1.0

    cached = _fx_cache.get(f"{from_ccy}{to_ccy}=X")
    if cached:
        return cached["rate"]

    cached_rev = _fx_cache.get(f"{to_ccy}{from_ccy}=X")
    if cached_rev and cached_rev["rate"]:
        return 1.0 / cached_rev["rate"]

    return None


async def get_history(ticker: str, range: str = "1y", interval: str = "1d") -> list[dict]:
    """Get historical prices.

    range: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
    interval: 1m, 5m, 15m, 1d, 1wk, 1mo
    """
    if not is_valid_ticker(ticker):
        logger.warning("Rejected invalid ticker format")
        return []
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
            meta = result["meta"]
            raw_ccy = meta.get("currency", "USD")
            timestamps = result.get("timestamp", [])
            quotes = result["indicators"]["quote"][0]
            closes = quotes.get("close", [])

            # Normalize subunit currency for historical closes (e.g. GBp pence -> GBP)
            _, divisor = normalize_currency(raw_ccy)

            # Use richer date format for intraday intervals so multiple points per day are distinct
            is_intraday = interval.endswith("m") and not interval.endswith("mo") or interval.endswith("h")
            fmt = "%Y-%m-%d %H:%M" if is_intraday else "%Y-%m-%d"
            history = []
            for i, ts in enumerate(timestamps):
                if i < len(closes) and closes[i] is not None:
                    history.append({
                        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
                        "close": round(closes[i] / divisor, 4),
                    })
            return history

    except Exception as e:
        logger.error(f"Yahoo history error for {ticker}: {e}")
        return []
