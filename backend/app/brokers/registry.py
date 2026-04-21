"""Broker registry.

Import this module to resolve an adapter by name. Adapters are registered at
import time; adding a new broker means adding it to the `_ADAPTERS` dict below.
"""
from __future__ import annotations

from app.brokers.base import BrokerAdapter, BrokerDescriptor
from app.brokers.saxo.adapter import SaxoAdapter

_ADAPTERS: dict[str, BrokerAdapter] = {
    "saxo": SaxoAdapter(),
}

_DESCRIPTORS: dict[str, BrokerDescriptor] = {
    "saxo": BrokerDescriptor(
        name="saxo",
        label="Saxo Bank",
        environments=["sim", "live"],
        trading_available=False,
    ),
}


def get_adapter(name: str) -> BrokerAdapter:
    try:
        return _ADAPTERS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown broker: {name!r}") from exc


def list_adapters() -> list[BrokerDescriptor]:
    return list(_DESCRIPTORS.values())
