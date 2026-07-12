from datetime import datetime
from pydantic import BaseModel


class SyncStatusResponse(BaseModel):
    source: str
    status: str
    records_synced: int
    synced_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}
