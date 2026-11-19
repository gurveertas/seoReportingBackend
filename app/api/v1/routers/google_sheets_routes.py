import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.integrations.googleSheets.client import get_sheets_client
from app.integrations.googleSheets.service import get_sheet_data
from app.requestModels.req_models import SheetsDataRequest

logger = logging.getLogger(__name__)
google_sheets_router = APIRouter()


def _credentials_path() -> str:
    default_path = (
        Path(__file__).resolve().parents[3]
        / "integrations"
        / "googleSheets"
        / "credentials"
        / "service-account.json"
    )
    return os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", str(default_path))


@google_sheets_router.get("/health")
def get_google_sheets_health():
    return {"status": True, "message": "Google Sheets routes are healthy"}


@google_sheets_router.post("/values")
def fetch_sheet_values(request: SheetsDataRequest):
    try:
        client = get_sheets_client(_credentials_path())
        values = get_sheet_data(
            service=client,
            spreadsheet_id=request.spreadsheet_id,
            range_name=request.range_name,
        )
    except Exception as error:
        logger.exception("Google Sheets values request failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve Google Sheets values.",
        ) from error

    return {
        "spreadsheet_id": request.spreadsheet_id,
        "range": request.range_name,
        "values": values,
    }
