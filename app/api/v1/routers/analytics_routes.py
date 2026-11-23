import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from google.auth.exceptions import RefreshError

from app.api.v1.routers.client_routes import (
    get_authenticated_workspace_id,
    get_client_integration_property,
    get_workspace_client,
)
from app.api.v1.routers.ga4_routes import _credentials_path as ga4_credentials_path
from app.api.v1.routers.gsc_routes import _credentials_path as gsc_credentials_path
from app.api.v1.routers.google_sheets_routes import (
    _credentials_path as sheets_credentials_path,
)
from app.database.connection import get_database
from app.integrations.credentials import build_source_client
from app.integrations.ga4.service import get_ga4_report
from app.integrations.googleSheets.service import get_sheet_data
from app.integrations.gsc.service import get_search_performance
from app.middlewares.protect_route import protect_route
from app.models.integration_data import (
    GA4ReportRecord,
    GoogleSheetsDataRecord,
    GSCSearchReportRecord,
)

logger = logging.getLogger(__name__)
analytics_router = APIRouter(dependencies=[Depends(protect_route)])

GA4_METRICS = ["totalUsers", "sessions", "screenPageViews"]
SHEETS_DEFAULT_RANGE = "A1:J100"


def parse_month(month: str | None) -> date | None:
    """'2026-10' -> date(2026, 10, 1). Raises 422 for bad input or future months."""
    if not month:
        return None
    try:
        year, month_number = (int(part) for part in month.split("-"))
        first = date(year, month_number, 1)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="month must look like YYYY-MM.") from error
    today = datetime.now(timezone.utc).date()
    if first >= today.replace(day=1):
        raise HTTPException(status_code=422, detail="Only completed months can be reported.")
    return first


def latest_reportable_month(today: date | None = None) -> date:
    """Search Console data lags 2-3 days, so a month is reportable from the 4th
    of the following month. Returns the first day of that month."""
    today = today or datetime.now(timezone.utc).date()
    previous = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    if today.day >= 4:
        return previous
    return (previous - timedelta(days=1)).replace(day=1)


DateBounds = tuple[date, date, date, date]


def _requested_bounds(
    start_date: date | None = None,
    end_date: date | None = None,
    comparison_start_date: date | None = None,
    comparison_end_date: date | None = None,
) -> DateBounds | None:
    if all(value is None for value in (
        start_date, end_date, comparison_start_date, comparison_end_date
    )):
        return None
    if start_date is None or end_date is None or start_date > end_date:
        raise HTTPException(422, "Provide start_date and end_date in chronological order.")
    if comparison_start_date is None and comparison_end_date is None:
        try:
            comparison_end_date = start_date - timedelta(days=1)
            comparison_start_date = comparison_end_date - (end_date - start_date)
        except OverflowError as error:
            raise HTTPException(422, "The preceding comparison range is outside supported dates.") from error
    if comparison_start_date is None or comparison_end_date is None or comparison_start_date > comparison_end_date:
        raise HTTPException(422, "Provide both comparison dates in chronological order.")
    return start_date, end_date, comparison_start_date, comparison_end_date


def _period_bounds(
    period: Literal["monthly", "weekly"],
    today: date | None = None,
    month: date | None = None,
) -> tuple[date, date, date, date]:
    today = today or datetime.now(timezone.utc).date()
    if period == "monthly" and month is not None:
        current_start = month.replace(day=1)
        next_month = (current_start + timedelta(days=32)).replace(day=1)
        current_end = next_month - timedelta(days=1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        return current_start, current_end, previous_start, previous_end
    if period == "monthly":
        current_start = today.replace(day=1) - timedelta(days=1)
        current_start = current_start.replace(day=1)
        current_end = today.replace(day=1) - timedelta(days=1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        return current_start, current_end, previous_start, previous_end

    current_week_start = today - timedelta(days=today.weekday())
    current_end = current_week_start - timedelta(days=1)
    current_start = current_end - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    return current_start, current_end, previous_start, previous_end


_RECORD_KEYS = {
    "ga4_reports": ("workspace_id", "client_id", "property_id", "start_date", "end_date", "dimension_headers"),
    "gsc_search_reports": ("workspace_id", "client_id", "site_url", "start_date", "end_date", "dimensions"),
    "google_sheets_reports": ("workspace_id", "client_id", "spreadsheet_id", "range_name"),
}


def _insert_record(collection_name: str, record: Any) -> str:
    """Store a snapshot. Re-running the same period overwrites it instead of
    piling up duplicates."""
    document = record.model_dump()
    key_fields = _RECORD_KEYS.get(collection_name)
    try:
        collection = get_database()[collection_name]
        if key_fields:
            key = {field: document.get(field) for field in key_fields}
            result = collection.find_one_and_replace(
                key, document, upsert=True, return_document=True, projection={"_id": 1}
            )
            return str(result["_id"])
        return str(collection.insert_one(document).inserted_id)
    except Exception as error:
        logger.exception("Unable to store %s data", collection_name)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to store {collection_name} data.",
        ) from error


def _fetch_and_store_ga4(
    workspace_id: str,
    client_id: str,
    property_id: str,
    client,
    start_date: str,
    end_date: str,
    dimensions: list[str],
) -> str:
    response = get_ga4_report(
        client=client,
        property_id=property_id,
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions,
        metrics=GA4_METRICS,
    )
    dimension_headers = [header.name for header in response.dimension_headers]
    metric_headers = [header.name for header in response.metric_headers]
    rows = [
        {
            "dimensions": {
                name: value.value
                for name, value in zip(dimension_headers, row.dimension_values)
            },
            "metrics": {
                name: value.value
                for name, value in zip(metric_headers, row.metric_values)
            },
        }
        for row in response.rows
    ]
    return _insert_record(
        "ga4_reports",
        GA4ReportRecord(
            workspace_id=workspace_id,
            client_id=client_id,
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            dimension_headers=dimension_headers,
            metric_headers=metric_headers,
            row_count=response.row_count,
            rows=rows,
        ),
    )


def _fetch_and_store_gsc(
    workspace_id: str,
    client_id: str,
    site_url: str,
    client,
    start_date: str,
    end_date: str,
    dimensions: list[str],
) -> str:
    rows = get_search_performance(
        service=client,
        site_url=site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions or None,
    )
    return _insert_record(
        "gsc_search_reports",
        GSCSearchReportRecord(
            workspace_id=workspace_id,
            client_id=client_id,
            site_url=site_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=dimensions,
            rows=rows,
        ),
    )


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    return int(numeric_value) if numeric_value.is_integer() else numeric_value


def _percent(value: Any) -> float | None:
    numeric_value = _number(value)
    return round(numeric_value * 100, 2) if numeric_value is not None else None


def _find_latest(collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
    return get_database()[collection].find_one(
        query,
        sort=[("fetched_at", -1)],
    )


def _authenticated_workspace_id(user: dict[str, Any]) -> str:
    return get_authenticated_workspace_id(user)


def _metric_value(record: dict[str, Any] | None, source: str, metric: str):
    if not record or not record.get("rows"):
        return None
    row = record["rows"][0]
    if source == "ga4":
        return _number(row.get("metrics", {}).get(metric))
    return _number(row.get(metric))


def _make_kpi(
    key: str,
    label: str,
    current: int | float | None,
    previous: int | float | None,
    change_unit: str = "percent",
) -> dict[str, Any]:
    if current is None or previous is None:
        change = None
        trend = "unavailable"
    elif change_unit == "percentage_points":
        change = round(current - previous, 2)
        trend = "up" if change > 0 else "down" if change < 0 else "steady"
    elif change_unit == "positions":
        change = round(previous - current, 2)
        trend = "up" if change > 0 else "down" if change < 0 else "steady"
    elif previous == 0:
        change = None
        trend = "unavailable"
    else:
        change = round(((current - previous) / abs(previous)) * 100, 2)
        trend = "up" if change > 0 else "down" if change < 0 else "steady"

    return {
        "key": key,
        "label": label,
        "value": current,
        "previous_value": previous,
        "change": change,
        "change_unit": change_unit,
        "trend": trend,
    }


def _ga4_daily_chart(record: dict[str, Any] | None) -> dict[str, Any]:
    rows = record.get("rows", []) if record else []
    rows = sorted(
        rows,
        key=lambda row: row.get("dimensions", {}).get("date", ""),
    )
    labels = [
        _format_ga4_date(row.get("dimensions", {}).get("date", ""))
        for row in rows
    ]
    return {
        "type": "line",
        "labels": labels,
        "datasets": [
            {
                "label": metric,
                "data": [
                    _number(row.get("metrics", {}).get(metric))
                    for row in rows
                ],
            }
            for metric in GA4_METRICS
        ],
    }


def _format_ga4_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _gsc_daily_chart(record: dict[str, Any] | None) -> dict[str, Any]:
    rows = record.get("rows", []) if record else []
    rows = sorted(rows, key=lambda row: (row.get("keys") or [""])[0])
    return {
        "type": "line",
        "labels": [(row.get("keys") or [""])[0] for row in rows],
        "datasets": [
            {
                "label": metric,
                "data": [_number(row.get(metric)) for row in rows],
            }
            for metric in ("clicks", "impressions")
        ],
    }


def _daily_table(
    record: dict[str, Any] | None,
    source: Literal["ga4", "gsc"],
) -> dict[str, Any]:
    stored_rows = (record or {}).get("rows", [])
    if source == "ga4":
        stored_rows = sorted(
            stored_rows,
            key=lambda row: row.get("dimensions", {}).get("date", ""),
        )
        columns = ["date", *GA4_METRICS]
        rows = [
            {
                "date": _format_ga4_date(
                    row.get("dimensions", {}).get("date", "")
                ),
                **{
                    metric: _number(row.get("metrics", {}).get(metric))
                    for metric in GA4_METRICS
                },
            }
            for row in stored_rows
        ]
    else:
        stored_rows = sorted(
            stored_rows,
            key=lambda row: (row.get("keys") or [""])[0],
        )
        columns = [
            "date",
            "clicks",
            "impressions",
            "ctr_percent",
            "position",
        ]
        rows = [
            {
                "date": (row.get("keys") or [""])[0],
                **{
                    "clicks": _number(row.get("clicks")),
                    "impressions": _number(row.get("impressions")),
                    "ctr_percent": _percent(row.get("ctr")),
                    "position": _number(row.get("position")),
                },
            }
            for row in stored_rows
        ]
    return {"columns": columns, "rows": rows}


def _sheets_table(record: dict[str, Any] | None) -> dict[str, Any]:
    values = record.get("values", []) if record else []
    if not values:
        return {"columns": [], "rows": []}

    width = max(len(row) for row in values)
    header_values = list(values[0]) + [""] * (width - len(values[0]))
    columns = []
    used_names = set()
    for index, value in enumerate(header_values, start=1):
        name = str(value).strip() or f"Column {index}"
        while name in used_names:
            name = f"{name}_{index}"
        used_names.add(name)
        columns.append(name)

    rows = []
    for values_row in values[1:]:
        padded_values = list(values_row) + [None] * (width - len(values_row))
        rows.append(dict(zip(columns, padded_values)))
    return {"columns": columns, "rows": rows}


def _dashboard_from_database(
    workspace_id: str,
    client_id: str,
    period: Literal["monthly", "weekly"],
    month: date | None = None,
    bounds: DateBounds | None = None,
):
    client = get_workspace_client(workspace_id, client_id)
    current_start, current_end, previous_start, previous_end = bounds or _period_bounds(period, month=month)
    current_filter = {
        "workspace_id": workspace_id,
        "client_id": client_id,
        "start_date": current_start.isoformat(),
        "end_date": current_end.isoformat(),
    }
    previous_filter = {
        "workspace_id": workspace_id,
        "client_id": client_id,
        "start_date": previous_start.isoformat(),
        "end_date": previous_end.isoformat(),
    }

    ga4_summary = _find_latest(
        "ga4_reports",
        {**current_filter, "dimension_headers": []},
    )
    ga4_previous = _find_latest(
        "ga4_reports",
        {**previous_filter, "dimension_headers": []},
    )
    ga4_daily = _find_latest(
        "ga4_reports",
        {**current_filter, "dimension_headers": ["date"]},
    )
    gsc_summary = _find_latest(
        "gsc_search_reports",
        {**current_filter, "dimensions": []},
    )
    gsc_previous = _find_latest(
        "gsc_search_reports",
        {**previous_filter, "dimensions": []},
    )
    gsc_daily = _find_latest(
        "gsc_search_reports",
        {**current_filter, "dimensions": ["date"]},
    )
    gsc_queries = _find_latest(
        "gsc_search_reports",
        {**current_filter, "dimensions": ["query"]},
    )
    gsc_pages = _find_latest(
        "gsc_search_reports",
        {**current_filter, "dimensions": ["page"]},
    )
    sheets = _find_latest(
        "google_sheets_reports",
        {"workspace_id": workspace_id, "client_id": client_id},
    )

    kpis = []
    for metric, label, change_unit in (
        ("clicks", "Search clicks", "percent"),
        ("impressions", "Search impressions", "percent"),
        ("ctr", "Click-through rate", "percentage_points"),
        ("position", "Average position", "positions"),
    ):
        current_value = _metric_value(gsc_summary, "gsc", metric)
        previous_value = _metric_value(gsc_previous, "gsc", metric)
        if metric == "ctr":
            current_value = (
                round(current_value * 100, 2)
                if current_value is not None
                else None
            )
            previous_value = (
                round(previous_value * 100, 2)
                if previous_value is not None
                else None
            )
        kpis.append(
            _make_kpi(
                f"gsc_{metric}",
                label,
                current_value,
                previous_value,
                change_unit,
            )
        )
    kpis.extend(
        _make_kpi(
            f"ga4_{metric}",
            label,
            _metric_value(ga4_summary, "ga4", metric),
            _metric_value(ga4_previous, "ga4", metric),
        )
        for metric, label in (
            ("totalUsers", "Users"),
            ("sessions", "Sessions"),
            ("screenPageViews", "Page views"),
        )
    )

    query_rows = []
    if gsc_queries:
        query_rows = sorted(
            [
                {
                    "query": (row.get("keys") or [""])[0],
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr_percent": _percent(row.get("ctr")),
                    "position": row.get("position", 0),
                }
                for row in gsc_queries.get("rows", [])
            ],
            key=lambda row: row["clicks"],
            reverse=True,
        )[:10]
    page_rows = []
    if gsc_pages:
        page_rows = sorted(
            [
                {
                    "page": (row.get("keys") or [""])[0],
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr_percent": _percent(row.get("ctr")),
                    "position": row.get("position", 0),
                }
                for row in gsc_pages.get("rows", [])
            ],
            key=lambda row: row["clicks"],
            reverse=True,
        )[:10]

    return {
        "client": {
            "client_id": client_id,
            "name": client["name"],
        },
        "period": {
            "mode": period,
            "start_date": current_start.isoformat(),
            "end_date": current_end.isoformat(),
            "comparison_start_date": previous_start.isoformat(),
            "comparison_end_date": previous_end.isoformat(),
        },
        "sources": {
            "gsc": {
                "status": "available" if gsc_summary or gsc_daily else "no_data",
                "fetched_at": (
                    (gsc_summary or gsc_daily or {}).get("fetched_at")
                ),
                "site_url": (
                    (
                        gsc_summary
                        or gsc_daily
                        or gsc_queries
                        or gsc_pages
                        or {}
                    ).get("site_url") or ((client.get("integrations") or {}).get("gsc") or {}).get("property_url")
                ),
            },
            "ga4": {
                "status": "available" if ga4_summary or ga4_daily else "no_data",
                "fetched_at": (
                    (ga4_summary or ga4_daily or {}).get("fetched_at")
                ),
            },
            "google_sheets": {
                "status": "available" if sheets else "no_data",
                "fetched_at": sheets.get("fetched_at") if sheets else None,
            },
        },
        "kpis": kpis,
        "charts": {
            "gsc_daily": _gsc_daily_chart(gsc_daily),
            "ga4_daily": _ga4_daily_chart(ga4_daily),
        },
        "tables": {
            "gsc_daily": _daily_table(gsc_daily, "gsc"),
            "ga4_daily": _daily_table(ga4_daily, "ga4"),
            "top_queries": {
                "columns": [
                    "query",
                    "clicks",
                    "impressions",
                    "ctr_percent",
                    "position",
                ],
                "rows": query_rows,
            },
            "top_pages": {
                "columns": [
                    "page",
                    "clicks",
                    "impressions",
                    "ctr_percent",
                    "position",
                ],
                "rows": page_rows,
            },
            "google_sheets": _sheets_table(sheets),
        },
    }


def _refresh_ga4(
    workspace_id: str,
    client_id: str,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
):
    property_id = get_client_integration_property(
        workspace_id,
        client_id,
        "ga4",
        "property_id",
    )
    client = build_source_client(
        get_workspace_client(workspace_id, client_id), "ga4", ga4_credentials_path()
    )
    record_ids = []
    for period_start, period_end in ((start, end), (previous_start, previous_end)):
        start_string = period_start.isoformat()
        end_string = period_end.isoformat()
        record_ids.append(
            _fetch_and_store_ga4(
                workspace_id,
                client_id,
                property_id,
                client,
                start_string,
                end_string,
                [],
            )
        )
        record_ids.append(
            _fetch_and_store_ga4(
                workspace_id,
                client_id,
                property_id,
                client,
                start_string,
                end_string,
                ["date"],
            )
        )
    return record_ids


def _refresh_gsc(
    workspace_id: str,
    client_id: str,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
):
    site_url = get_client_integration_property(
        workspace_id,
        client_id,
        "gsc",
        "property_url",
    )
    client = build_source_client(
        get_workspace_client(workspace_id, client_id), "gsc", gsc_credentials_path()
    )
    record_ids = []
    for period_start, period_end in ((start, end), (previous_start, previous_end)):
        start_string = period_start.isoformat()
        end_string = period_end.isoformat()
        record_ids.append(
            _fetch_and_store_gsc(
                workspace_id,
                client_id,
                site_url,
                client,
                start_string,
                end_string,
                [],
            )
        )
        record_ids.append(
            _fetch_and_store_gsc(
                workspace_id,
                client_id,
                site_url,
                client,
                start_string,
                end_string,
                ["date"],
            )
        )
    for dimension in ("query", "page"):
        record_ids.append(
            _fetch_and_store_gsc(
                workspace_id,
                client_id,
                site_url,
                client,
                start.isoformat(),
                end.isoformat(),
                [dimension],
            )
        )
    return record_ids


def _refresh_sheets(workspace_id: str, client_id: str):
    spreadsheet_id = get_client_integration_property(
        workspace_id,
        client_id,
        "google_sheets",
        "property_id",
    )
    client = build_source_client(
        get_workspace_client(workspace_id, client_id), "google_sheets", sheets_credentials_path()
    )
    values = get_sheet_data(
        service=client,
        spreadsheet_id=spreadsheet_id,
        range_name=SHEETS_DEFAULT_RANGE,
    )
    return _insert_record(
        "google_sheets_reports",
        GoogleSheetsDataRecord(
            workspace_id=workspace_id,
            client_id=client_id,
            spreadsheet_id=spreadsheet_id,
            range_name=SHEETS_DEFAULT_RANGE,
            values=values,
        ),
    )


def _refresh_status(function, *args) -> dict[str, Any]:
    try:
        record_ids = function(*args)
        if record_ids is None:
            return {"status": "refreshed"}
        if isinstance(record_ids, list):
            return {"status": "refreshed", "record_ids": record_ids}
        return {"status": "refreshed", "record_id": record_ids}
    except HTTPException as error:
        if error.status_code == 409 and "Google account" in str(error.detail):
            return {"status": "error", "detail": error.detail}
        if error.status_code in (404, 409):
            return {"status": "not_configured", "detail": error.detail}
        logger.exception("Integration refresh failed")
        return {"status": "error", "detail": "Integration refresh failed."}
    except RefreshError:
        logger.warning("Google token refresh failed", exc_info=True)
        return {
            "status": "error",
            "detail": "Google access expired or was revoked. Reconnect the Google account in Settings.",
        }
    except Exception:
        logger.exception("Integration refresh failed")
        return {"status": "error", "detail": "Integration refresh failed."}


@analytics_router.get("/monthly")
def get_monthly_analytics(
    client_id: str,
    month: str | None = None,
    user: dict[str, Any] = Depends(protect_route),
    bounds: DateBounds | None = Depends(_requested_bounds),
):
    workspace_id = _authenticated_workspace_id(user)
    if bounds is not None:
        return _dashboard_from_database(workspace_id, client_id, "monthly", bounds=bounds)
    month_start = parse_month(month)
    if month_start is None:
        return _dashboard_from_database(workspace_id, client_id, "monthly")
    return _dashboard_from_database(workspace_id, client_id, "monthly", month_start)


@analytics_router.get("/weekly")
def get_weekly_analytics(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
    bounds: DateBounds | None = Depends(_requested_bounds),
):
    workspace_id = _authenticated_workspace_id(user)
    return _dashboard_from_database(workspace_id, client_id, "weekly", bounds=bounds)


@analytics_router.post("/refresh")
def refresh_analytics(
    client_id: str,
    period: Literal["monthly", "weekly"] = "monthly",
    month: str | None = None,
    user: dict[str, Any] = Depends(protect_route),
    bounds: DateBounds | None = Depends(_requested_bounds),
):
    month_start = parse_month(month) if period == "monthly" and bounds is None else None
    workspace_id = _authenticated_workspace_id(user)
    refresh = refresh_sources(workspace_id, client_id, period, month_start, bounds=bounds)
    if bounds is not None:
        dashboard = _dashboard_from_database(workspace_id, client_id, period, bounds=bounds)
    elif month_start is None:
        dashboard = _dashboard_from_database(workspace_id, client_id, period)
    else:
        dashboard = _dashboard_from_database(workspace_id, client_id, period, month_start)
    dashboard["refresh"] = refresh
    return dashboard


def refresh_sources(
    workspace_id: str,
    client_id: str,
    period: Literal["monthly", "weekly"],
    month_start: date | None = None,
    bounds: DateBounds | None = None,
) -> dict[str, Any]:
    if bounds is not None:
        start, end, previous_start, previous_end = bounds
    elif month_start is None:
        start, end, previous_start, previous_end = _period_bounds(period)
    else:
        start, end, previous_start, previous_end = _period_bounds(period, month=month_start)
    return {
        "ga4": _refresh_status(
            _refresh_ga4,
            workspace_id,
            client_id,
            start,
            end,
            previous_start,
            previous_end,
        ),
        "gsc": _refresh_status(
            _refresh_gsc,
            workspace_id,
            client_id,
            start,
            end,
            previous_start,
            previous_end,
        ),
        "google_sheets": _refresh_status(
            _refresh_sheets,
            workspace_id,
            client_id,
        ),
    }
