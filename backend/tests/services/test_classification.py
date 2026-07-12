"""Classification service: asset_type upsert, source precedence, bulk lookup."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from app.services import classification as classification_svc


async def test_set_and_get_classification(db, user_id):
    row = await classification_svc.set_classification(
        db, user_id, "AAPL", "equity", source="user"
    )
    assert row.asset_type == "equity"
    assert row.source == "user"
    assert row.symbol == "AAPL"

    fetched = await classification_svc.get_classification(db, user_id, "AAPL")
    assert fetched is not None
    assert fetched.asset_type == "equity"


async def test_auto_does_not_overwrite_manual(db, user_id):
    """If the user (or agent) has already classified a symbol, 'auto' must not overwrite it."""
    await classification_svc.set_classification(db, user_id, "SPY", "etf", source="user")

    # Try to re-classify as auto, should be ignored
    row = await classification_svc.set_classification(db, user_id, "SPY", "equity", source="auto")
    assert row.asset_type == "etf"
    assert row.source == "user"


async def test_agent_overwrites_auto(db, user_id):
    await classification_svc.set_classification(db, user_id, "VT", "equity", source="auto")
    row = await classification_svc.set_classification(db, user_id, "VT", "etf", source="agent")
    assert row.asset_type == "etf"
    assert row.source == "agent"


async def test_user_overwrites_agent(db, user_id):
    await classification_svc.set_classification(db, user_id, "QQQ", "etf", source="agent")
    row = await classification_svc.set_classification(db, user_id, "QQQ", "equity", source="user")
    assert row.asset_type == "equity"
    assert row.source == "user"


async def test_invalid_asset_type_rejected(db, user_id):
    with pytest.raises(ValueError):
        await classification_svc.set_classification(db, user_id, "AAPL", "not-a-type", source="user")


async def test_invalid_source_rejected(db, user_id):
    with pytest.raises(ValueError):
        await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="hacker")


async def test_bulk_lookup_default_for_unclassified(db, user_id):
    await classification_svc.set_classification(db, user_id, "AAPL", "equity", source="auto")
    await classification_svc.set_classification(db, user_id, "SPY", "etf", source="auto")

    result = await classification_svc.get_asset_types_bulk(
        db, user_id, ["AAPL", "SPY", "UNKNOWN-TICKER"]
    )
    assert result == {"AAPL": "equity", "SPY": "etf", "UNKNOWN-TICKER": "equity"}


async def test_hardcoded_indexes_classified_as_etf_without_network(db, user_id):
    """Known ETF tickers bypass yfinance lookup, so this test is network-safe."""
    # SPY is in _KNOWN_INDEX_TICKERS, should classify without hitting Yahoo
    asset_type, source = await classification_svc.auto_detect_asset_type("SPY")
    assert asset_type == "etf"
    assert source == "auto"

    asset_type, _ = await classification_svc.auto_detect_asset_type("VT")
    assert asset_type == "etf"

    asset_type, _ = await classification_svc.auto_detect_asset_type("^GSPC")
    assert asset_type == "index"

    asset_type, _ = await classification_svc.auto_detect_asset_type("BTC-USD")
    assert asset_type == "crypto"


async def test_cash_classified_as_cash(db, user_id):
    asset_type, _ = await classification_svc.auto_detect_asset_type("CASH")
    assert asset_type == "cash"


async def test_unknown_symbol_falls_back_to_equity_when_yahoo_fails(db, user_id):
    """If yfinance lookup fails, fallback is 'equity': safe default for analysis."""
    with patch("app.services.classification._fetch_quote_type_from_yahoo", return_value=None):
        asset_type, _ = await classification_svc.auto_detect_asset_type("OBSCURE-TICKER-XYZ")
    assert asset_type == "equity"


async def test_yahoo_quote_type_maps_correctly(db, user_id):
    with patch("app.services.classification._fetch_quote_type_from_yahoo", return_value="EQUITY"):
        at, _ = await classification_svc.auto_detect_asset_type("MSFT")
        assert at == "equity"

    with patch("app.services.classification._fetch_quote_type_from_yahoo", return_value="ETF"):
        at, _ = await classification_svc.auto_detect_asset_type("FOO")
        assert at == "etf"

    with patch("app.services.classification._fetch_quote_type_from_yahoo", return_value="CRYPTOCURRENCY"):
        at, _ = await classification_svc.auto_detect_asset_type("DOGE-USD")
        assert at == "crypto"
