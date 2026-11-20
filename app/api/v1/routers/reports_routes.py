from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.v1.routers.analytics_routes import (
    _authenticated_workspace_id,
    _dashboard_from_database,
)
from app.middlewares.protect_route import protect_route
from app.reports.analytics_pdf import generate_analytics_pdf

reports_router = APIRouter(dependencies=[Depends(protect_route)])


def _report_response(
    period: Literal["monthly", "weekly"],
    client_id: str,
    user: dict[str, Any],
) -> StreamingResponse:
    dashboard = _dashboard_from_database(
        _authenticated_workspace_id(user),
        client_id,
        period,
    )
    client_name = dashboard["client"]["name"]
    pdf_content = generate_analytics_pdf(dashboard, period, client_name)
    period_data = dashboard.get("period", {})
    start_date = period_data.get("start_date", "report")
    end_date = period_data.get("end_date", "")
    filename = f"seo-report-{period}-{start_date}-{end_date}.pdf"
    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@reports_router.get("/monthly", response_class=StreamingResponse)
def get_monthly_report(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
) -> StreamingResponse:
    return _report_response("monthly", client_id, user)


@reports_router.get("/weekly", response_class=StreamingResponse)
def get_weekly_report(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
) -> StreamingResponse:
    return _report_response("weekly", client_id, user)
