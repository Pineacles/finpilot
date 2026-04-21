"""Saxo → domain DTO translations.

Keep all knowledge of Saxo's payload shapes here. The adapter calls into these
helpers so it can stay focused on auth + flow control.
"""
from __future__ import annotations

from app.brokers.base import BrokerAccount, BrokerBalance, BrokerPosition


def account_from_saxo(raw: dict, environment: str) -> BrokerAccount:
    return BrokerAccount(
        external_id=raw["AccountKey"],
        display_name=raw.get("DisplayName") or raw.get("AccountId") or raw["AccountKey"],
        currency=raw.get("Currency", "USD"),
        environment=environment,
    )


def accounts_from_saxo(body: dict, environment: str) -> list[BrokerAccount]:
    return [account_from_saxo(a, environment) for a in body.get("Data", [])]


def balance_from_saxo(raw: dict, account_external_id: str) -> BrokerBalance:
    currency = raw.get("Currency", "USD")
    cash = _num(raw.get("CashBalance"))
    total = _num(raw.get("TotalValue"))
    unrealized = _num(raw.get("UnrealizedMarginProfitLoss") or raw.get("UnrealizedPositionsValue"))
    return BrokerBalance(
        account_external_id=account_external_id,
        cash=cash,
        currency=currency,
        total_value=total if raw.get("TotalValue") is not None else None,
        unrealized_pnl=unrealized if raw.get("UnrealizedMarginProfitLoss") is not None or raw.get("UnrealizedPositionsValue") is not None else None,
    )


def positions_from_saxo(body: dict, account_external_id: str) -> list[BrokerPosition]:
    out: list[BrokerPosition] = []
    for raw in body.get("Data", []):
        display = raw.get("DisplayAndFormat", {}) or {}
        base = raw.get("PositionBase", {}) or raw.get("NetPositionBase", {}) or {}
        view = raw.get("PositionView", {}) or raw.get("NetPositionView", {}) or {}

        # Saxo's Symbol field often carries an exchange suffix ("AAPL:xnas",
        # "SHEL:xlon"). The ticker before the colon is the instrument symbol
        # that everything else (yfinance, display, lookup cache) understands.
        raw_symbol = display.get("Symbol") or str(raw.get("NetPositionId") or "UNKNOWN")
        symbol = raw_symbol.split(":", 1)[0].upper()
        name = display.get("Description") or symbol
        currency = display.get("Currency") or base.get("AccountingCurrency") or "USD"
        quantity = _num(base.get("Amount"))
        avg_price = _num(base.get("OpenPrice"))
        market_price = view.get("CurrentPrice")
        market_value = view.get("MarketValue")
        unrealized = view.get("ProfitLossOnTrade")

        out.append(BrokerPosition(
            account_external_id=account_external_id,
            symbol=symbol,
            name=name,
            quantity=quantity,
            avg_price=avg_price,
            currency=currency,
            market_price=_num(market_price) if market_price is not None else None,
            market_value=_num(market_value) if market_value is not None else None,
            unrealized_pnl=_num(unrealized) if unrealized is not None else None,
        ))
    return out


def _num(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
