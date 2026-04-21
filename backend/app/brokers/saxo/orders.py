"""Saxo order payload construction + DTOs.

All order shape knowledge lives here. Adapter methods call these helpers so
mapping bugs stay isolated to one module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

BuySell = Literal["Buy", "Sell"]
OrderType = Literal["Market", "Limit", "Stop", "StopLimit"]
Duration = Literal["DayOrder", "GoodTillCancel"]


@dataclass(frozen=True)
class OrderRequest:
    account_key: str
    uic: int
    asset_type: str
    buy_sell: BuySell
    amount: float
    order_type: OrderType
    duration: Duration = "DayOrder"
    limit_price: float | None = None
    stop_price: float | None = None
    manual: bool = True

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "AccountKey": self.account_key,
            "Uic": self.uic,
            "AssetType": self.asset_type,
            "BuySell": self.buy_sell,
            "Amount": self.amount,
            "OrderType": self.order_type,
            "OrderDuration": {"DurationType": self.duration},
            "ManualOrder": self.manual,
        }
        if self.order_type in ("Limit", "StopLimit") and self.limit_price is not None:
            payload["OrderPrice"] = self.limit_price
        if self.order_type in ("Stop", "StopLimit") and self.stop_price is not None:
            payload["StopLimitPrice"] = self.stop_price
        return payload


@dataclass(frozen=True)
class PrecheckResult:
    ok: bool
    estimated_cash_required: float | None
    estimated_fees: float | None
    currency: str | None
    warnings: list[str]
    error_message: str | None

    @classmethod
    def from_saxo(cls, body: dict[str, Any]) -> "PrecheckResult":
        result = (body.get("PreCheckResult") or "").lower()
        err = body.get("ErrorInfo") or {}
        warnings = []
        # Saxo returns things like `EstimatedCostsInInstrumentCurrency`
        cost = body.get("EstimatedCashRequired")
        fees = body.get("EstimatedCommissions")
        currency = body.get("Currency")
        if body.get("OrderFlagsAndStatus", {}).get("Warnings"):
            warnings = [str(w) for w in body["OrderFlagsAndStatus"]["Warnings"]]
        return cls(
            ok=result == "ok",
            estimated_cash_required=float(cost) if cost is not None else None,
            estimated_fees=float(fees) if fees is not None else None,
            currency=currency,
            warnings=warnings,
            error_message=err.get("Message") if err else None,
        )


@dataclass(frozen=True)
class OrderAck:
    order_id: str
    raw: dict[str, Any]

    @classmethod
    def from_saxo(cls, body: dict[str, Any]) -> "OrderAck":
        oid = body.get("OrderId") or str(body.get("Orders", [{}])[0].get("OrderId", ""))
        if not oid:
            raise ValueError("saxo order response missing OrderId")
        return cls(order_id=str(oid), raw=body)


@dataclass(frozen=True)
class OrderSummary:
    order_id: str
    symbol: str
    uic: int
    asset_type: str
    buy_sell: str
    amount: float
    order_type: str
    status: str
    price: float | None

    @classmethod
    def from_saxo(cls, raw: dict[str, Any]) -> "OrderSummary":
        display = raw.get("DisplayAndFormat", {}) or {}
        raw_symbol = display.get("Symbol") or ""
        symbol = raw_symbol.split(":", 1)[0].upper() if raw_symbol else ""
        return cls(
            order_id=str(raw.get("OrderId", "")),
            symbol=symbol,
            uic=int(raw.get("Uic") or 0),
            asset_type=raw.get("AssetType") or "",
            buy_sell=raw.get("BuySell") or "",
            amount=float(raw.get("Amount") or 0),
            order_type=raw.get("OpenOrderType") or raw.get("OrderType") or "",
            status=raw.get("Status") or "",
            price=float(raw["Price"]) if raw.get("Price") is not None else None,
        )
