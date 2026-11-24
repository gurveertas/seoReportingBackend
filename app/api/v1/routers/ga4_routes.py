import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.integrations.credentials import build_source_client
from app.integrations.ga4.service import get_ga4_report
from app.api.v1.routers.client_routes import (
    get_authenticated_workspace_id,
    get_client_integration_property,
    get_workspace_client,
)
from app.database.connection import get_database
from app.middlewares.protect_route import protect_route
from app.models.integration_data import GA4ReportRecord
from app.requestModels.req_models import GA4ReportRequest

logger = logging.getLogger(__name__)
ga4_router = APIRouter(dependencies=[Depends(protect_route)])


@ga4_router.get("/health")
def get_ga4_health(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
):
    get_workspace_client(
        get_authenticated_workspace_id(user),
        client_id,
    )
    return {"status": True, "message": "GA4 routes are healthy"}


@ga4_router.post("/report")
def fetch_ga4_report(
    client_id: str,
    request: GA4ReportRequest,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    property_id = get_client_integration_property(
        workspace_id,
        client_id,
        "ga4",
        "property_id",
    )
    client = build_source_client(get_workspace_client(workspace_id, client_id), "ga4")
    try:
        response = get_ga4_report(
            client=client,
            property_id=property_id,
            start_date=request.start_date,
            end_date=request.end_date,
            dimensions=request.dimensions,
            metrics=request.metrics,
        )
    except Exception as error:
        logger.exception("GA4 report request failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve the GA4 report.",
        ) from error

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
    record = GA4ReportRecord(
        workspace_id=workspace_id,
        client_id=client_id,
        property_id=property_id,
        start_date=request.start_date,
        end_date=request.end_date,
        dimension_headers=dimension_headers,
        metric_headers=metric_headers,
        row_count=response.row_count,
        rows=rows,
    )
    try:
        insert_result = get_database()["ga4_reports"].insert_one(
            record.model_dump()
        )
    except Exception as error:
        logger.exception("Unable to store GA4 report data")
        raise HTTPException(
            status_code=500,
            detail="Unable to store the GA4 report.",
        ) from error

    return {
        "dimension_headers": dimension_headers,
        "metric_headers": metric_headers,
        "row_count": response.row_count,
        "rows": rows,
        "record_id": str(insert_result.inserted_id),
    }
