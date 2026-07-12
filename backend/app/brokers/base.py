"""Broker adapter interface and domain DTOs.

Nothing broker-specific lives here. Every adapter maps its native payloads to
these types before returning.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession


class AuthState(str, enum.Enum):
    DISABLED = "disabled"
    SETUP_REQUIRED = "setup_required"
    NEEDS_AUTH = "needs_auth"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass(frozen=True)
class BrokerAccount:
    external_id: str
    display_name: str
    currency: str
    environment: str


@dataclass(frozen=True)
class BrokerBalance:
    account_external_id: str
    cash: float
    currency: str
    total_value: float | None = None
    unrealized_pnl: float | None = None


@dataclass(frozen=True)
class BrokerPosition:
    account_external_id: str
    symbol: str
    name: str
    quantity: float
    avg_price: float
    currency: str
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None


@dataclass(frozen=True)
class ConnectionStatus:
    state: AuthState
    environment: str | None = None
    detail: str | None = None
    last_error: str | None = None


class BrokerAdapter(ABC):
    """Abstract broker integration.

    Implementations are instantiated once per adapter and scoped per call by
    passing `(db, user_id)` into each method. Persistence (tokens, flags) lives
    in the DB; adapters must not hold mutable per-user state on the instance.
    """

    name: str

    @abstractmethod
    async def is_enabled(self, db: AsyncSession, user_id: str) -> bool: ...

    @abstractmethod
    async def is_configured(self, db: AsyncSession, user_id: str) -> bool: ...

    @abstractmethod
    async def authenticate(self, db: AsyncSession, user_id: str) -> ConnectionStatus: ...

    @abstractmethod
    async def status(self, db: AsyncSession, user_id: str) -> ConnectionStatus: ...

    @abstractmethod
    async def disconnect(self, db: AsyncSession, user_id: str) -> None: ...

    @abstractmethod
    async def health_check(self, db: AsyncSession, user_id: str) -> bool: ...

    @abstractmethod
    async def get_accounts(self, db: AsyncSession, user_id: str) -> list[BrokerAccount]: ...

    @abstractmethod
    async def get_balances(self, db: AsyncSession, user_id: str, account_key: str) -> BrokerBalance: ...

    @abstractmethod
    async def get_positions(self, db: AsyncSession, user_id: str, account_key: str) -> list[BrokerPosition]: ...


@dataclass
class BrokerDescriptor:
    """Static metadata about a registered broker, safe to expose via API."""

    name: str
    label: str
    environments: list[str] = field(default_factory=list)
    trading_available: bool = False
