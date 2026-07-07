"""Response schemas for portfolio positions, trades, and valuation
(app.api.endpoints.portfolio / app.services.portfolio_service)."""
from pydantic import BaseModel


class PositionOut(BaseModel):
    id: str
    symbol: str
    name: str
    quantity: float
    avg_cost_price: float
    currency: str
    fx_rate: float | None = None
    last_price: float | None
    last_price_at: str | None = None
    change: float
    change_pct: float
    market_value: float
    unrealized_pnl: float
    pnl_pct: float
    weight_pct: float
    first_bought: str | None
    trade_count: int
    earnings_date: str | None
    sparkline: list[float]
    asset_type: str = "equity"  # equity|etf|index|crypto|bond|commodity|cash — from SymbolClassification
    price_stale: bool = False  # quote fetch failed this request AND last known price is >15min old
    fx_unavailable: bool = False  # no CHF rate known for this currency — market_value/unrealized_pnl are 0.0, not real


class PortfolioResponse(BaseModel):
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    cash_balance: float
    net_deposits: float
    base_currency: str
    fx_rates: dict[str, float]
    positions_count: int
    positions: list[PositionOut]
    warnings: list[str] = []  # e.g. failed quote/FX fetches this request — never silent


class TradeExecutionResponse(BaseModel):
    """Two shapes depending on trade type: cash deposit/withdraw returns
    `cash_balance`; buy/sell returns symbol/type/quantity/price/currency."""
    status: str
    cash_balance: float | None = None
    symbol: str | None = None
    type: str | None = None
    quantity: float | None = None
    price: float | None = None
    currency: str | None = None


class TradeHistoryItem(BaseModel):
    id: str
    symbol: str
    type: str
    quantity: float
    price: float
    fees: float
    currency: str
    date: str
    total: float
    total_chf: float
    fees_chf: float


class ValueTimelineTrade(BaseModel):
    symbol: str
    type: str
    quantity: float
    price: float


class ValueTimelinePoint(BaseModel):
    date: str
    value: float
    cost: float
    pnl: float
    trades: list[ValueTimelineTrade] | None = None


class PortfolioHistoryPoint(BaseModel):
    date: str
    value: float
    pnl: float


class ClassificationOut(BaseModel):
    symbol: str
    asset_type: str
    source: str
    updated_at: str


class PublicShareStatusResponse(BaseModel):
    enabled: bool
    token: str | None
