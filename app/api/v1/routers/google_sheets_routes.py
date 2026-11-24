import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.integrations.credentials import build_source_client
from app.integrations.googleSheets.service import get_sheet_data
from app.api.v1.routers.client_routes import (
    get_authenticated_workspace_id,
    get_client_integration_property,
    get_workspace_client,
)
from app.database.connection import get_database
from app.middlewares.protect_route import protect_route
from app.models.integration_data import GoogleSheetsDataRecord
from app.requestModels.req_models import SheetsDataRequest

logger = logging.getLogger(__name__)
google_sheets_router = APIRouter(dependencies=[Depends(protect_route)])


@google_sheets_router.get("/health")
def get_google_sheets_health(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
):
    get_workspace_client(
        get_authenticated_workspace_id(user),
        client_id,
    )
    return {"status": True, "message": "Google Sheets routes are healthy"}


@google_sheets_router.post("/values")
def fetch_sheet_values(
    client_id: str,
    request: SheetsDataRequest,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    spreadsheet_id = get_client_integration_property(
        workspace_id,
        client_id,
        "google_sheets",
        "property_id",
    )
    client = build_source_client(get_workspace_client(workspace_id, client_id), "google_sheets")
    try:
        values = get_sheet_data(
            service=client,
            spreadsheet_id=spreadsheet_id,
            range_name=request.range_name,
        )
    except Exception as error:
        logger.exception("Google Sheets values request failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve Google Sheets values.",
        ) from error

    record = GoogleSheetsDataRecord(
        workspace_id=workspace_id,
        client_id=client_id,
        spreadsheet_id=spreadsheet_id,
        range_name=request.range_name,
        values=values,
    )
    try:
        insert_result = get_database()["google_sheets_reports"].insert_one(
            record.model_dump()
        )
    except Exception as error:
        logger.exception("Unable to store Google Sheets data")
        raise HTTPException(
            status_code=500,
            detail="Unable to store Google Sheets data.",
        ) from error

    return {
        "spreadsheet_id": spreadsheet_id,
        "range": request.range_name,
        "values": values,
        "record_id": str(insert_result.inserted_id),
    }
