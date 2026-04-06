from datetime import datetime, date
from pydantic import BaseModel


class StockPositionResponse(BaseModel):
    id: str
    symbol: str
    name: str
    quantity: float
    avg_cost_price: float
    currency: str
    last_price: float | None
    last_price_at: datetime | None
    unrealized_pnl: float | None
    market_value: float | None = None
    weight_pct: float | None = None

    model_config = {"from_attributes": True}


class PortfolioSummary(BaseModel):
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    positions_count: int
    positions: list[StockPositionResponse]


class PortfolioSnapshotResponse(BaseModel):
    snapshot_date: date
    total_value: float
    total_cost: float
    total_pnl: float

    model_config = {"from_attributes": True}


class StockTransactionResponse(BaseModel):
    id: str
    symbol: str
    type: str
    quantity: float
    price: float
    fees: float
    currency: str
    executed_at: datetime

    model_config = {"from_attributes": True}


class SyncResponse(BaseModel):
    status: str
    records_synced: int
    message: str


class SyncStatusResponse(BaseModel):
    source: str
    status: str
    records_synced: int
    synced_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}
