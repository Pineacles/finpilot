"""Response schemas for transaction categorization (app.api.endpoints.categorize)."""
from pydantic import BaseModel


class ManualCategorizeResponse(BaseModel):
    status: str
    updated: int
    merchant: str
    renamed_to: str | None = None
    renamed: int | None = None


class BulkCategorizeResponse(BaseModel):
    status: str
    updated: int


class AICategorizeResult(BaseModel):
    id: str
    category_id: str | None
    category_name: str
    confidence: float


class AICategorizeResponse(BaseModel):
    status: str
    sent: int
    categorized: int
    results: list[AICategorizeResult]
