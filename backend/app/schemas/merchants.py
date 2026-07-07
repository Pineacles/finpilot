"""Response/request schemas for merchant auto-categorization rules."""
from pydantic import BaseModel


class MerchantResponse(BaseModel):
    id: str
    name: str
    patterns: str
    default_category_id: str | None
    category_name: str | None = None
    is_system: bool

    model_config = {"from_attributes": True}


class MerchantCreate(BaseModel):
    name: str
    patterns: str  # pipe-separated
    default_category_id: str | None = None


class MerchantUpdate(BaseModel):
    name: str | None = None
    patterns: str | None = None
    default_category_id: str | None = None
