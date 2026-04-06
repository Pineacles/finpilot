from datetime import datetime
from pydantic import BaseModel


class AnalysisResponse(BaseModel):
    id: str
    analysis_type: str
    content: dict
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunAnalysisRequest(BaseModel):
    analysis_type: str = "position"  # macro|sector|position
