from typing import List, Optional

from pydantic import BaseModel, Field

class GSCIntegration(BaseModel):
    enabled : bool = True
    property_url : str

class GA4Integration(BaseModel):
    enabled : bool = True
    property_url : str
class GoogleSheetsIntegration(BaseModel):
    enabled : bool = True
    property_url : str

class Integrations(BaseModel):
    gsc: GSCIntegration = GSCIntegration(enabled=True, property_url="")
    ga4: GA4Integration = GA4Integration(enabled=True, property_url="")
    google_sheets: GoogleSheetsIntegration = GoogleSheetsIntegration(enabled=True, property_url="")

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