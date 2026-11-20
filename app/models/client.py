from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class GSCIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    property_url: str


class GA4Integration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    property_id: str


class SheetsIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    property_id: str


class Integrations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gsc: GSCIntegration | None = None
    ga4: GA4Integration | None = None
    google_sheets: SheetsIntegration | None = None


class Client(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    name: str = Field(min_length=1, max_length=120)
    integrations: Integrations = Field(default_factory=Integrations)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
