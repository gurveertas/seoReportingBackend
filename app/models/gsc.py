from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

class Period(BaseModel):
    type: Literal["weekly", "monthly"]
    start_date: str
    end_date: str

class GSCMetrics(BaseModel):
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0

class GSCDocument(BaseModel):
    workspace_id: str
    client_id: str
    property_url: str
    period: Period
    metrics: GSCMetrics
    dimension_type: str = "aggregate"
    dimension_key: str = "all"
    dimension_dict: dict = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))