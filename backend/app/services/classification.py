"""Asset-type classification for symbols.

Used to cleanly split individual-stock holdings from index/ETF holdings when
benchmarking vs S&P 500. Persisted per-user in symbol_classifications so users
(and the AI agent) can override the auto-detected type.

Classification sources, in order of authority:
  1. User override (source='user')
  2. Agent override (source='agent')
  3. Auto (yfinance quoteType + hardcoded well-known-index fallback)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import SymbolClassification

logger = logging.getLogger(__name__)

VALID_ASSET_TYPES = {"equity", "etf", "index", "crypto", "bond", "commodity", "cash"}
DEFAULT_ASSET_TYPE = "equity"

# Fallback list when yfinance lookup fails — well-known S&P / world / region indexes
# and the most common total-market / tech ETFs. Keeps the card correct even when
# the network lookup breaks.
_KNOWN_INDEX_TICKERS: dict[str, str] = {
    # Direct indexes
    "^GSPC": "index", "^DJI": "index", "^IXIC": "index", "^RUT": "index",
    "^STOXX50E": "index", "^FTSE": "index", "^GDAXI": "index", "^N225": "index",
    "^SSMI": "index", "^HSI": "index",
    # US broad-market ETFs
    "SPY": "etf", "VOO": "etf", "IVV": "etf", "VTI": "etf", "ITOT": "etf", "SCHB": "etf",
    "QQQ": "etf", "DIA": "etf", "IWM": "etf", "IWV": "etf",
    # World / region ETFs
    "VT": "etf", "VXUS": "etf", "VEA": "etf", "VWO": "etf",
    "IWDA": "etf", "VWCE": "etf", "EUNL": "etf", "ISAC": "etf", "FWIA": "etf",
    # Sector / bond
    "XLK": "etf", "XLF": "etf", "XLE": "etf", "XLV": "etf",
    "AGG": "etf", "BND": "etf", "TLT": "etf",
    # Crypto-like
    "BTC-USD": "crypto", "ETH-USD": "crypto",
}

# yfinance quoteType → our asset_type
_QUOTE_TYPE_MAP: dict[str, str] = {
    "EQUITY": "equity",
    "ETF": "etf",
    "MUTUALFUND": "etf",       # Treat mutual funds like ETFs for benchmarking purposes
    "INDEX": "index",
    "CURRENCY": "cash",
    "CRYPTOCURRENCY": "crypto",
    "FUTURE": "commodity",
}


async def _fetch_quote_type_from_yahoo(symbol: str) -> str | None:
    """Return quoteType from Yahoo Finance chart meta, or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "5d"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code != 200:
                return None
            meta = resp.json()["chart"]["result"][0]["meta"]
            return (meta.get("instrumentType") or "").upper() or None
    except Exception as e:
        logger.warning(f"quoteType lookup failed for {symbol}: {e}")
        return None


def _hardcoded_or_default(symbol: str) -> str:
    """Last-resort classification when yfinance gives us nothing."""
    return _KNOWN_INDEX_TICKERS.get(symbol.upper(), DEFAULT_ASSET_TYPE)


async def auto_detect_asset_type(symbol: str) -> tuple[str, str]:
    """Return (asset_type, source). Source is always 'auto' here."""
    symbol = symbol.upper().strip()
    if symbol == "CASH":
        return ("cash", "auto")

    # Hardcoded list first — it's instant and covers the most common benchmarks
    # even when the network is unreliable.
    if symbol in _KNOWN_INDEX_TICKERS:
        return (_KNOWN_INDEX_TICKERS[symbol], "auto")

    raw = await _fetch_quote_type_from_yahoo(symbol)
    if raw and raw in _QUOTE_TYPE_MAP:
        return (_QUOTE_TYPE_MAP[raw], "auto")

    return (_hardcoded_or_default(symbol), "auto")


async def get_classification(
    db: AsyncSession, user_id: str, symbol: str
) -> SymbolClassification | None:
    result = await db.execute(
        select(SymbolClassification).where(and_(
            SymbolClassification.user_id == user_id,
            SymbolClassification.symbol == symbol.upper(),
        ))
    )
    return result.scalar_one_or_none()


async def get_asset_types_bulk(
    db: AsyncSession, user_id: str, symbols: list[str]
) -> dict[str, str]:
    """Batch lookup — returns {symbol_upper: asset_type}. Unclassified → default."""
    if not symbols:
        return {}
    symbols_upper = [s.upper() for s in symbols]
    result = await db.execute(
        select(SymbolClassification).where(and_(
            SymbolClassification.user_id == user_id,
            SymbolClassification.symbol.in_(symbols_upper),
        ))
    )
    existing = {r.symbol: r.asset_type for r in result.scalars().all()}
    return {s: existing.get(s, DEFAULT_ASSET_TYPE) for s in symbols_upper}


async def set_classification(
    db: AsyncSession,
    user_id: str,
    symbol: str,
    asset_type: str,
    source: str,
) -> SymbolClassification:
    """Upsert a classification. `source` must be 'auto', 'user', or 'agent'."""
    if asset_type not in VALID_ASSET_TYPES:
        raise ValueError(f"invalid asset_type: {asset_type}")
    if source not in {"auto", "user", "agent"}:
        raise ValueError(f"invalid source: {source}")

    symbol = symbol.upper().strip()
    existing = await get_classification(db, user_id, symbol)
    if existing:
        # Don't let 'auto' overwrite a manual classification — manual takes priority.
        if source == "auto" and existing.source in {"user", "agent"}:
            return existing
        existing.asset_type = asset_type
        existing.source = source
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return existing

    row = SymbolClassification(
        user_id=user_id, symbol=symbol, asset_type=asset_type, source=source,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def ensure_classified(
    db: AsyncSession, user_id: str, symbol: str
) -> SymbolClassification:
    """Return existing classification or create one via auto-detection."""
    existing = await get_classification(db, user_id, symbol)
    if existing:
        return existing
    asset_type, source = await auto_detect_asset_type(symbol)
    return await set_classification(db, user_id, symbol, asset_type, source)


async def backfill_user_classifications(
    db: AsyncSession, user_id: str
) -> dict[str, int]:
    """Classify every symbol the user owns or has ever traded that isn't already
    classified. Returns {'created': N, 'skipped': M}."""
    from app.models.stock import StockPosition, StockTransaction

    # Collect all symbols this user has touched
    pos_result = await db.execute(
        select(StockPosition.symbol).where(StockPosition.user_id == user_id).distinct()
    )
    tx_result = await db.execute(
        select(StockTransaction.symbol).where(StockTransaction.user_id == user_id).distinct()
    )
    symbols = {s for s in pos_result.scalars().all()} | {s for s in tx_result.scalars().all()}

    # Which are already classified?
    existing_result = await db.execute(
        select(SymbolClassification.symbol).where(SymbolClassification.user_id == user_id)
    )
    already = set(existing_result.scalars().all())

    created = 0
    skipped = len(already)
    for sym in symbols:
        if sym.upper() in already:
            continue
        try:
            await ensure_classified(db, user_id, sym)
            created += 1
        except Exception as e:
            logger.warning(f"backfill classify failed for {sym}: {e}")

    return {"created": created, "skipped": skipped, "total_symbols": len(symbols)}
