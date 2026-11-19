from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class GSCIntegration(BaseModel):
    enabled: bool = True
    property_url: str

class GA4Integration(BaseModel):
    enabled: bool = True
    property_id: str

class SheetsIntegration(BaseModel):
    enabled: bool = True
    property_id: str

class Integrations(BaseModel):
    gsc: Optional[GSCIntegration] = None
    ga4: Optional[GA4Integration] = None
    google_sheets: Optional[SheetsIntegration] = None

class ReportSettings(BaseModel):
    weekly: bool = True
    monthly: bool = True
    timezone: str = "Asia/Kolkata"

class Client(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str
    name: str
    website: str
    integrations: Integrations
    report_settings: ReportSettings = Field(default_factory=ReportSettings)
    status: str = "active"
    createdAt: datetime = Field(default_factory=lambda:datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda:datetime.now(timezone.utc))

