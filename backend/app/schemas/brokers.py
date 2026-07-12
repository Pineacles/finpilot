"""Response/request schemas for broker adapter endpoints (app.api.endpoints.brokers)."""
from pydantic import BaseModel


# ── OAuth / connection status ────────────────────────────────────

class ConnectResponse(BaseModel):
    authorize_url: str
    environment: str


class StatusResponse(BaseModel):
    state: str
    environment: str | None
    detail: str | None = None
    last_error: str | None = None


class CallbackPayload(BaseModel):
    code: str
    state: str


class DisconnectResponse(BaseModel):
    status: str


class HealthResponse(BaseModel):
    ok: bool


# ── Broker metadata ───────────────────────────────────────────────

class SaxoEnvironmentOption(BaseModel):
    value: str
    label: str
    enabled: bool


class BrokerMeta(BaseModel):
    name: str
    label: str
    environments: list[str]
    trading_available: bool


class BrokersListResponse(BaseModel):
    brokers: list[BrokerMeta]
    saxo_environments: list[SaxoEnvironmentOption]


# ── Accounts / balances / positions ───────────────────────────────

class SaxoAccount(BaseModel):
    external_id: str
    display_name: str
    currency: str
    environment: str


class SaxoAccountsResponse(BaseModel):
    accounts: list[SaxoAccount]


class SaxoBalanceResponse(BaseModel):
    account_external_id: str
    cash: float
    currency: str
    total_value: float | None = None
    unrealized_pnl: float | None = None


class SaxoPosition(BaseModel):
    account_external_id: str
    symbol: str
    name: str
    quantity: float
    avg_price: float
    currency: str
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None


class SaxoPositionsResponse(BaseModel):
    positions: list[SaxoPosition]


# ── Sync ───────────────────────────────────────────────────────────

class SaxoSyncResponse(BaseModel):
    status: str
    account_id: str | None = None
    cash_balance: float | None = None
    cash_currency: str | None = None
    positions_upserted: int | None = None
    positions_removed: int | None = None
    reason: str | None = None


# ── Sub-portfolio (local-DB slice for the portfolio page's Saxo card) ────

class SaxoSubPortfolioPosition(BaseModel):
    id: str
    symbol: str
    name: str
    quantity: float
    avg_cost_price: float
    currency: str
    last_price: float | None
    unrealized_pnl: float | None
    market_value: float


class SaxoSubPortfolioAccount(BaseModel):
    account_id: str
    name: str
    currency: str
    cash: float
    cash_updated_at: str | None
    positions: list[SaxoSubPortfolioPosition]


class SaxoSubPortfolioResponse(BaseModel):
    connected: bool
    accounts: list[SaxoSubPortfolioAccount]
