from datetime import datetime

from pydantic import BaseModel


class ColumnMappingSchema(BaseModel):
    date_col: str
    amount_col: str | None = None
    description_col: str | None = None
    debit_col: str | None = None
    credit_col: str | None = None
    date_format: str = "%d.%m.%Y"
    decimal_separator: str = "."
    invert_amount: bool = False
    currency: str = "CHF"


class CsvPreviewResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, str]]
    delimiter: str
    encoding: str


class ImportProfileCreate(BaseModel):
    name: str
    account_id: str | None = None
    mapping: ColumnMappingSchema


class ImportProfileResponse(BaseModel):
    id: str
    name: str
    account_id: str | None
    mapping: dict
    created_at: datetime

    model_config = {"from_attributes": True}
