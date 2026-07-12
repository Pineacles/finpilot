"""Response schemas for sync endpoints (app.api.endpoints.sync).

SyncStatusResponse lives in app.schemas.stock (shared with the broker sync
history model); this module holds the sync-trigger response.
"""
from pydantic import BaseModel


class GmailPollResponse(BaseModel):
    status: str
    new_transactions: int
    balance: float | None
    errors: list[str]
