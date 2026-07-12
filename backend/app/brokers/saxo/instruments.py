"""Saxo instrument lookup: resolves FinPilot symbols to Saxo Uic + AssetType.

Saxo's order endpoints take a numeric Uic, not a ticker. Given a symbol like
"AAPL" or "SHEL.L", we search `/ref/v1/instruments` and pick the best stock
match. Results are cached per-process to keep subsequent trades fast.

Kept deliberately simple: no fuzzy ranking, no multi-exchange disambiguation
beyond what Saxo's Keywords query provides. For ambiguous symbols the caller
can pass `asset_type`/`exchange_id` hints.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.brokers.saxo.client import SaxoHTTPClient, SaxoHTTPError


@dataclass(frozen=True)
class SaxoInstrument:
    uic: int
    symbol: str
    description: str
    asset_type: str
    currency: str
    exchange_id: str | None


class InstrumentNotFound(LookupError):
    def __init__(self, symbol: str):
        super().__init__(f"no Saxo instrument found for symbol {symbol!r}")
        self.symbol = symbol


_CACHE: dict[tuple[str, str], SaxoInstrument] = {}
_CACHE_LOCK = asyncio.Lock()


async def lookup(
    client: SaxoHTTPClient,
    *,
    access_token: str,
    symbol: str,
    asset_type: str = "Stock",
) -> SaxoInstrument:
    """Resolve a ticker to a Saxo instrument. Cached per (symbol, asset_type).

    Returns the first instrument whose Saxo symbol matches the input exactly.
    If no exact match is found, falls back to the first search result.
    """
    key = (symbol.upper(), asset_type)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    async with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached

        body = await client.authed_get(
            "/ref/v1/instruments",
            access_token=access_token,
            params={
                "Keywords": symbol,
                "AssetTypes": asset_type,
                "$top": 20,
            },
        )
        rows = body.get("Data", []) if isinstance(body, dict) else []
        if not rows:
            raise InstrumentNotFound(symbol)

        target = symbol.upper()
        exact = next((r for r in rows if (r.get("Symbol") or "").upper() == target), None)
        chosen = exact or rows[0]

        instrument = SaxoInstrument(
            uic=int(chosen["Identifier"]),
            symbol=chosen.get("Symbol", symbol),
            description=chosen.get("Description", ""),
            asset_type=chosen.get("AssetType", asset_type),
            currency=chosen.get("CurrencyCode", ""),
            exchange_id=chosen.get("ExchangeId"),
        )
        _CACHE[key] = instrument
        return instrument


def _reset_cache_for_tests() -> None:
    """Testing hook; never call from production code."""
    _CACHE.clear()
