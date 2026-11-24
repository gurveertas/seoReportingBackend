from datetime import date
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.models.client import Integrations


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1)
    fullname: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    username: str
    password: str


class WorkspaceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fullname: str | None = Field(default=None, min_length=1, max_length=120)
    openai_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one workspace field must be provided.")
        if "fullname" in self.model_fields_set:
            if self.fullname is None or not self.fullname.strip():
                raise ValueError("fullname cannot be empty.")
            self.fullname = self.fullname.strip()
        return self


class ClientCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    integrations: Integrations = Field(default_factory=Integrations)
    comparison: bool = False
    auto_monthly: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty.")
        return normalized


class ClientUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    integrations: Integrations | None = None
    comparison: bool = False
    auto_monthly: bool | None = None

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one client field must be provided.")
        if "auto_monthly" in self.model_fields_set and self.auto_monthly is None:
            raise ValueError("auto_monthly cannot be null.")
        if "name" in self.model_fields_set:
            if self.name is None or not self.name.strip():
                raise ValueError("name cannot be empty.")
            self.name = self.name.strip()
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


class SiteImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    name: str | None = Field(default=None, max_length=120)
    ga4_property_id: str | None = Field(default=None, max_length=40)


class SiteImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sites: List[SiteImportItem] = Field(min_length=1, max_length=200)
    auto_monthly: bool = True


class ReportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start_date: date | None = None
    end_date: date | None = None
    comparison_start_date: date | None = None
    comparison_end_date: date | None = None

    comparison: bool = False
    next_plans: list[str] = Field(default_factory=list, alias="next-plans")


class ReportGenerateRequest(ReportOptions):
    model_config = ConfigDict(extra="forbid")

    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    refresh: bool = True
