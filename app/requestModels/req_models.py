from typing import List, Optional

from pydantic import BaseModel, Field

class Integrations(BaseModel):
    gsc: bool = True
    ga4: bool = True
    google_sheets: bool = True

class RegisterRequest(BaseModel):
    username: str
    password: str
    fullname: str
    integrations: Integrations 

class LoginRequest(BaseModel):
    username: str
    password: str


class GA4ReportRequest(BaseModel):
    property_id: str
    start_date: str
    end_date: str
    dimensions: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(
        default_factory=lambda: ["totalUsers", "sessions", "screenPageViews"]
    )


class SheetsDataRequest(BaseModel):
    spreadsheet_id: str
    range_name: str


class GSCSearchRequest(BaseModel):
    site_url: str
    start_date: str
    end_date: str
    dimensions: Optional[List[str]] = None