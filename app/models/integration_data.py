from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class IntegrationDataRecord(BaseModel):
    workspace_id: str
    client_id: str
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class GA4ReportRecord(IntegrationDataRecord):
    property_id: str
    start_date: str
    end_date: str
    dimension_headers: list[str]
    metric_headers: list[str]
    row_count: int
    rows: list[dict[str, dict[str, str]]]


class GSCSearchReportRecord(IntegrationDataRecord):
    site_url: str
    start_date: str
    end_date: str
    dimensions: list[str] | None = None
    rows: list[dict[str, Any]]


class GSCSitesRecord(IntegrationDataRecord):
    sites: list[dict[str, Any]]


class GoogleSheetsDataRecord(IntegrationDataRecord):
    spreadsheet_id: str
    range_name: str
    values: list[list[Any]]
