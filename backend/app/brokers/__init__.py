"""Pluggable broker integrations.

Each broker is implemented as a `BrokerAdapter` (see `.base`) and registered
in `.registry`. The rest of the app interacts with brokers only through the
abstract interface and the domain DTOs in `.base` — broker-specific payload
shapes never leak out of an adapter module.
"""
from app.brokers.base import (
    AuthState,
    BrokerAccount,
    BrokerAdapter,
    BrokerBalance,
    BrokerPosition,
    ConnectionStatus,
)
from app.brokers.registry import get_adapter, list_adapters

__all__ = [
    "AuthState",
    "BrokerAccount",
    "BrokerAdapter",
    "BrokerBalance",
    "BrokerPosition",
    "ConnectionStatus",
    "get_adapter",
    "list_adapters",
]
