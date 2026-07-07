"""Response schemas for the watchlist (app.api.endpoints.watchlist /
app.services.watchlist_service). Tracking only — no analysis, no
recommendations."""
from pydantic import BaseModel


class WatchlistItemOut(BaseModel):
    id: str
    symbol: str
    added_at: str | None
    price: float | None
    change: float | None
    change_pct: float | None
    currency: str | None
    name: str | None
    quote_unavailable: bool = False
