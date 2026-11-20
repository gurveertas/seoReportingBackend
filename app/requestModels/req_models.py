from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.client import Integrations as ClientIntegrations

class GSCIntegration(BaseModel):
    enabled : bool = True
    property_url : str

class GA4Integration(BaseModel):
    enabled : bool = True
    property_id : str
class GoogleSheetsIntegration(BaseModel):
    enabled : bool = True
    property_id : str

class Integrations(BaseModel):
    gsc: GSCIntegration = GSCIntegration(enabled=True, property_url="")
    ga4: GA4Integration = GA4Integration(enabled=True, property_id="")
    google_sheets: GoogleSheetsIntegration = GoogleSheetsIntegration(enabled=True, property_id="")

class RegisterRequest(BaseModel):
    username: str
    password: str
    fullname: str
    integrations: Integrations 

class LoginRequest(BaseModel):
    username: str
    password: str


class ClientUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fullname: str | None = Field(default=None, min_length=1, max_length=100)
    integrations: ClientIntegrations | None = None

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one client field must be provided.")
        if "fullname" in self.model_fields_set:
            if self.fullname is None or not self.fullname.strip():
                raise ValueError("fullname cannot be empty.")
            self.fullname = self.fullname.strip()
        if "integrations" in self.model_fields_set and self.integrations is None:
            raise ValueError("integrations cannot be null.")
        return self


class GA4ReportRequest(BaseModel):
    start_date: str
    end_date: str
    dimensions: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(
        default_factory=lambda: ["totalUsers", "sessions", "screenPageViews"]
    )


class SheetsDataRequest(BaseModel):
    range_name: str


class GSCSearchRequest(BaseModel):
    start_date: str
    end_date: str
    dimensions: Optional[List[str]] = None