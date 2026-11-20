from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one workspace field must be provided.")
        if self.fullname is None or not self.fullname.strip():
            raise ValueError("fullname cannot be empty.")
        self.fullname = self.fullname.strip()
        return self


class ClientCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    integrations: Integrations = Field(default_factory=Integrations)

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

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one client field must be provided.")
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
