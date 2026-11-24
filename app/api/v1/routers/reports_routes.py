from io import BytesIO
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.v1.routers.analytics_routes import (
    DateBounds,
    _requested_bounds,
    _authenticated_workspace_id,
    _dashboard_from_database,
    latest_reportable_month,
    parse_month,
)
from app.api.v1.routers.client_routes import get_workspace_client
from app.middlewares.protect_route import protect_route
from app.integrations.workspace_secrets import workspace_secret
from app.reports.analytics_pdf import generate_analytics_pdf
from app.reports.storage import (
    ReportGenerationError,
    delete_report,
    generate_monthly_report,
    get_report,
    last_runs,
    list_reports,
    read_report_file,
    report_filename,
)
from app.requestModels.req_models import ReportGenerateRequest, ReportOptions

reports_router = APIRouter(dependencies=[Depends(protect_route)])
workspace_reports_router = APIRouter(dependencies=[Depends(protect_route)])


def _pdf_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


def _report_bounds(payload: ReportOptions) -> DateBounds | None:
    return _requested_bounds(
        payload.start_date, payload.end_date,
        payload.comparison_start_date, payload.comparison_end_date,
    )


def _report_response(
    period: Literal["monthly", "weekly"],
    client_id: str,
    user: dict[str, Any],
    month: str | None = None,
    comparison: bool = False,
    next_plans: list[str] | None = None,
    bounds: DateBounds | None = None,
) -> StreamingResponse:
    workspace_id = _authenticated_workspace_id(user)
    month_start = parse_month(month) if period == "monthly" else None
    if bounds is not None:
        dashboard = _dashboard_from_database(workspace_id, client_id, period, bounds=bounds)
    elif month_start is None:
        dashboard = _dashboard_from_database(workspace_id, client_id, period)
    else:
        dashboard = _dashboard_from_database(workspace_id, client_id, period, month_start)
    client_name = dashboard["client"]["name"]
    pdf_content = generate_analytics_pdf(
        dashboard, period, client_name, comparison=comparison, next_plans=next_plans,
        openai_api_key=workspace_secret(workspace_id, "openai_api_key_enc"),
        google_cloud_console_key=workspace_secret(workspace_id, "google_cloud_console_key_enc"),
    )
    period_data = dashboard.get("period", {})
    start_date = period_data.get("start_date", "report")
    end_date = period_data.get("end_date", "")
    filename = f"seo-report-{period}-{start_date}-{end_date}.pdf"
    return _pdf_response(pdf_content, filename)


@reports_router.get("", include_in_schema=True)
def get_client_reports(client_id: str, user: dict[str, Any] = Depends(protect_route)):
    workspace_id = _authenticated_workspace_id(user)
    get_workspace_client(workspace_id, client_id)
    return {
        "reports": list_reports(workspace_id, client_id),
        "runs": last_runs(workspace_id, client_id),
        "latest_reportable_month": f"{latest_reportable_month():%Y-%m}",
    }


@reports_router.post("/monthly/generate", status_code=201)
def generate_and_store_monthly_report(
    client_id: str,
    payload: ReportGenerateRequest | None = None,
    user: dict[str, Any] = Depends(protect_route),
):
    payload = payload or ReportGenerateRequest()
    workspace_id = _authenticated_workspace_id(user)
    bounds = _report_bounds(payload)
    default_month = bounds[0].replace(day=1) if bounds else latest_reportable_month()
    month_start = parse_month(payload.month) or default_month
    try:
        report = generate_monthly_report(
            workspace_id, client_id, month_start, refresh=payload.refresh, trigger="manual",
            comparison=payload.comparison, next_plans=payload.next_plans, bounds=bounds,
        )
    except ReportGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"report": report}


@reports_router.get("/monthly", response_class=StreamingResponse)
def get_monthly_report(
    client_id: str,
    month: str | None = None,
    comparison: bool = False,
    next_plans: Annotated[list[str] | None, Query(alias="next-plans")] = None,
    user: dict[str, Any] = Depends(protect_route),
) -> StreamingResponse:
    return _report_response("monthly", client_id, user, month, comparison, next_plans)


@reports_router.post("/monthly", response_class=StreamingResponse)
def create_monthly_pdf(
    client_id: str,
    payload: ReportGenerateRequest | None = None,
    user: dict[str, Any] = Depends(protect_route),
) -> StreamingResponse:
    result = generate_and_store_monthly_report(client_id, payload, user)
    return download_report(client_id, result["report"]["report_id"], user)


@reports_router.get("/weekly", response_class=StreamingResponse)
def get_weekly_report(
    client_id: str,
    comparison: bool = False,
    next_plans: Annotated[list[str] | None, Query(alias="next-plans")] = None,
    user: dict[str, Any] = Depends(protect_route),
) -> StreamingResponse:
    return _report_response("weekly", client_id, user, comparison=comparison, next_plans=next_plans)


@reports_router.post("/weekly/generate", response_class=StreamingResponse)
def generate_weekly_report(
    client_id: str,
    payload: ReportOptions,
    user: dict[str, Any] = Depends(protect_route),
) -> StreamingResponse:
    return _report_response(
        "weekly", client_id, user, comparison=payload.comparison, next_plans=payload.next_plans,
        bounds=_report_bounds(payload),
    )


def _owned_report(user: dict[str, Any], report_id: str, client_id: str | None = None) -> dict[str, Any]:
    report = get_report(_authenticated_workspace_id(user), report_id)
    if not report or (client_id and report["client_id"] != client_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@reports_router.get("/{report_id}/download", response_class=StreamingResponse)
def download_report(client_id: str, report_id: str, user: dict[str, Any] = Depends(protect_route)):
    report = _owned_report(user, report_id, client_id)
    return _pdf_response(read_report_file(report), report.get("filename") or "report.pdf")


@reports_router.delete("/{report_id}")
def remove_report(client_id: str, report_id: str, user: dict[str, Any] = Depends(protect_route)):
    delete_report(_owned_report(user, report_id, client_id))
    return {"status": True}


@workspace_reports_router.get("")
def get_workspace_reports(user: dict[str, Any] = Depends(protect_route)):
    """Latest reports across every website in the workspace."""
    return {
        "reports": list_reports(_authenticated_workspace_id(user), limit=200),
        "latest_reportable_month": f"{latest_reportable_month():%Y-%m}",
    }


__all__ = ["reports_router", "workspace_reports_router", "report_filename"]
