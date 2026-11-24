"""Generate, store and list monthly PDF reports.

PDFs live in MongoDB GridFS (bucket `report_files`) so they survive redeploys on
hosts with ephemeral disks. Metadata lives in `reports`; every attempt, good or
bad, is written to `report_runs` (the run log).
"""

import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Literal

import gridfs
import requests
from bson import ObjectId

from app.database.connection import get_database
from app.integrations.workspace_secrets import workspace_secret
from app.reports.analytics_pdf import generate_analytics_pdf

logger = logging.getLogger(__name__)

REPORTS = "reports"
RUNS = "report_runs"
BUCKET = "report_files"
Trigger = Literal["manual", "scheduled"]


class ReportGenerationError(RuntimeError):
    pass


def _bucket() -> gridfs.GridFSBucket:
    return gridfs.GridFSBucket(get_database(), bucket_name=BUCKET)


def _ensure_indexes() -> None:
    database = get_database()
    database[REPORTS].create_index(
        [("workspace_id", 1), ("client_id", 1), ("period", 1), ("month", 1)], unique=True
    )
    database[RUNS].create_index([("workspace_id", 1), ("client_id", 1), ("created_at", -1)])


def report_filename(client_name: str, month_start: date) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", client_name).strip("_") or "Client"
    return f"{safe}_Monthly_{month_start:%Y%m}.pdf"


def public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": str(report["_id"]),
        "client_id": report["client_id"],
        "client_name": report.get("client_name"),
        "period": report.get("period", "monthly"),
        "month": report.get("month"),
        "start_date": report.get("start_date"),
        "end_date": report.get("end_date"),
        "filename": report.get("filename"),
        "size": report.get("size"),
        "trigger": report.get("trigger"),
        "warnings": report.get("warnings", []),
        "created_at": report.get("created_at"),
    }


def _log_run(
    workspace_id: str,
    client_id: str,
    month: str,
    status: str,
    started: float,
    trigger: Trigger,
    error: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    get_database()[RUNS].insert_one(
        {
            "workspace_id": workspace_id,
            "client_id": client_id,
            "period": "monthly",
            "month": month,
            "status": status,
            "error": error,
            "warnings": warnings or [],
            "trigger": trigger,
            "duration_seconds": round(time.monotonic() - started, 2),
            "created_at": datetime.now(timezone.utc),
        }
    )


def _notify_failure(client_name: str, month: str, error: str) -> None:
    url = os.getenv("NOTIFY_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(url, json={"text": f"Monthly report failed for {client_name} ({month}): {error}"}, timeout=10)
    except requests.RequestException:
        logger.warning("Failure notification could not be sent")


def generate_monthly_report(
    workspace_id: str,
    client_id: str,
    month_start: date,
    refresh: bool = True,
    trigger: Trigger = "manual",
    comparison: bool = False,
    next_plans: list[str] | None = None,
    bounds: tuple[date, date, date, date] | None = None,
) -> dict[str, Any]:
    """Pull fresh data (optional), render the PDF and store it, replacing any
    earlier report for the same month. Never stores a partial report: if
    Search Console or a configured GA4 property fails, nothing is saved."""
    # Imported here to avoid a circular import with the analytics router.
    from app.api.v1.routers.analytics_routes import _dashboard_from_database, refresh_sources
    from app.api.v1.routers.client_routes import get_workspace_client

    _ensure_indexes()
    started = time.monotonic()
    month = f"{month_start:%Y-%m}"
    client = get_workspace_client(workspace_id, client_id)
    warnings: list[str] = []

    try:
        if refresh:
            result = refresh_sources(workspace_id, client_id, "monthly", month_start, bounds=bounds)
            gsc = result.get("gsc", {})
            if gsc.get("status") == "not_configured":
                raise ReportGenerationError("Search Console is not set up for this website.")
            for source, label in (("gsc", "Search Console"), ("ga4", "Google Analytics")):
                if result.get(source, {}).get("status") == "error":
                    raise ReportGenerationError(
                        f"{label}: {result[source].get('detail') or 'the data pull failed.'}"
                    )
            if result.get("google_sheets", {}).get("status") == "error":
                warnings.append("Google Sheets data could not be read; that section was left out.")

        dashboard = _dashboard_from_database(workspace_id, client_id, "monthly", month_start, bounds=bounds)
        if dashboard.get("sources", {}).get("gsc", {}).get("status") != "available":
            raise ReportGenerationError("No Search Console data is stored for this month yet.")
        pdf_bytes = generate_analytics_pdf(
            dashboard, "monthly", client["name"], comparison=comparison, next_plans=next_plans,
            openai_api_key=workspace_secret(workspace_id, "openai_api_key_enc"),
            google_cloud_console_key=workspace_secret(workspace_id, "google_cloud_console_key_enc"),
        )
    except ReportGenerationError as error:
        _log_run(workspace_id, client_id, month, "failed", started, trigger, str(error))
        if trigger == "scheduled":
            _notify_failure(client["name"], month, str(error))
        raise
    except Exception as error:
        logger.exception("Report generation crashed")
        _log_run(workspace_id, client_id, month, "failed", started, trigger, "Unexpected error while building the report.")
        if trigger == "scheduled":
            _notify_failure(client["name"], month, error.__class__.__name__)
        raise ReportGenerationError("Unexpected error while building the report.") from error

    filename = report_filename(client["name"], month_start)
    bucket = _bucket()
    file_id = bucket.upload_from_stream(
        filename,
        pdf_bytes,
        metadata={"workspace_id": workspace_id, "client_id": client_id, "content_type": "application/pdf"},
    )
    database = get_database()
    key = {"workspace_id": workspace_id, "client_id": client_id, "period": "monthly", "month": month}
    previous = database[REPORTS].find_one(key)
    now = datetime.now(timezone.utc)
    database[REPORTS].update_one(
        key,
        {
            "$set": {
                "client_name": client["name"],
                "start_date": dashboard["period"]["start_date"],
                "end_date": dashboard["period"]["end_date"],
                "filename": filename,
                "file_id": file_id,
                "size": len(pdf_bytes),
                "trigger": trigger,
                "warnings": warnings,
                "created_at": now,
            }
        },
        upsert=True,
    )
    if previous and previous.get("file_id"):
        try:
            bucket.delete(previous["file_id"])
        except gridfs.errors.NoFile:
            pass
    _log_run(workspace_id, client_id, month, "success", started, trigger, warnings=warnings)
    return public_report(database[REPORTS].find_one(key))


def list_reports(workspace_id: str, client_id: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"workspace_id": workspace_id}
    if client_id:
        query["client_id"] = client_id
    cursor = get_database()[REPORTS].find(query).sort([("month", -1), ("created_at", -1)]).limit(limit)
    return [public_report(report) for report in cursor]


def last_runs(workspace_id: str, client_id: str, limit: int = 10) -> list[dict[str, Any]]:
    cursor = get_database()[RUNS].find({"workspace_id": workspace_id, "client_id": client_id}).sort("created_at", -1).limit(limit)
    return [
        {
            "month": run.get("month"),
            "status": run.get("status"),
            "error": run.get("error"),
            "warnings": run.get("warnings", []),
            "trigger": run.get("trigger"),
            "duration_seconds": run.get("duration_seconds"),
            "created_at": run.get("created_at"),
        }
        for run in cursor
    ]


def get_report(workspace_id: str, report_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(report_id):
        return None
    return get_database()[REPORTS].find_one({"_id": ObjectId(report_id), "workspace_id": workspace_id})


def read_report_file(report: dict[str, Any]) -> bytes:
    return _bucket().open_download_stream(report["file_id"]).read()


def delete_report(report: dict[str, Any]) -> None:
    try:
        _bucket().delete(report["file_id"])
    except gridfs.errors.NoFile:
        pass
    get_database()[REPORTS].delete_one({"_id": report["_id"]})


def delete_client_reports(workspace_id: str, client_id: str) -> None:
    for report in get_database()[REPORTS].find({"workspace_id": workspace_id, "client_id": client_id}):
        delete_report(report)
    get_database()[RUNS].delete_many({"workspace_id": workspace_id, "client_id": client_id})
