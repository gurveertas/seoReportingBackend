import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.integrations.gsc.client import get_gsc_client
from app.integrations.gsc.service import get_search_performance, get_gsc_sites
from app.api.v1.routers.client_routes import (
    get_authenticated_workspace_id,
    get_client_integration_property,
    get_workspace_client,
)
from app.database.connection import get_database
from app.middlewares.protect_route import protect_route
from app.models.gsc import GSCDocument
from app.models.integration_data import GSCSearchReportRecord, GSCSitesRecord
from app.requestModels.req_models import GSCSearchRequest

logger = logging.getLogger(__name__)
gsc_router = APIRouter(dependencies=[Depends(protect_route)])


def save_gsc_data(data: GSCDocument):
    document = data.model_dump()
    return get_database().gsc_data.update_one(
        {
            "workspace_id": document["workspace_id"],
            "client_id": document["client_id"],
            "property_url": document["property_url"],
            "period.type": document["period"]["type"],
            "period.start_date": document["period"]["start_date"],
            "period.end_date": document["period"]["end_date"],
            "dimension_type": document["dimension_type"],
            "dimension_key": document["dimension_key"],
        },
        {"$set": document},
        upsert=True,
    )


def _credentials_path() -> str:
    default_path = (
        Path(__file__).resolve().parents[3]
        / "integrations"
        / "gsc"
        / "credentials"
        / "service-account.json"
    )
    return os.getenv("GSC_CREDENTIALS_PATH", str(default_path))


@gsc_router.get('/health')
async def get_gsc_health(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
):
    get_workspace_client(
        get_authenticated_workspace_id(user),
        client_id,
    )
    return {"status":True, "message":"GSC routes are healthy"}


@gsc_router.get("/sites")
def fetch_gsc_sites(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    get_workspace_client(workspace_id, client_id)
    try:
        client = get_gsc_client(_credentials_path())
        sites = get_gsc_sites(client)
    except Exception as error:
        logger.exception("GSC sites request failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve GSC sites.",
        ) from error

    record = GSCSitesRecord(
        workspace_id=workspace_id,
        client_id=client_id,
        sites=sites,
    )
    try:
        insert_result = get_database()["gsc_sites"].insert_one(
            record.model_dump()
        )
    except Exception as error:
        logger.exception("Unable to store GSC sites")
        raise HTTPException(
            status_code=500,
            detail="Unable to store GSC sites.",
        ) from error

    return {"sites": sites, "record_id": str(insert_result.inserted_id)}


@gsc_router.post("/search-performance")
def fetch_gsc_search_performance(
    client_id: str,
    request: GSCSearchRequest,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    site_url = get_client_integration_property(
        workspace_id,
        client_id,
        "gsc",
        "property_url",
    )
    try:
        client = get_gsc_client(_credentials_path())
        rows = get_search_performance(
            service=client,
            site_url=site_url,
            start_date=request.start_date,
            end_date=request.end_date,
            dimensions=request.dimensions,
        )
    except Exception as error:
        logger.exception("GSC search performance request failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve GSC search performance.",
        ) from error

    record = GSCSearchReportRecord(
        workspace_id=workspace_id,
        client_id=client_id,
        site_url=site_url,
        start_date=request.start_date,
        end_date=request.end_date,
        dimensions=request.dimensions,
        rows=rows,
    )
    try:
        insert_result = get_database()["gsc_search_reports"].insert_one(
            record.model_dump()
        )
    except Exception as error:
        logger.exception("Unable to store GSC search performance data")
        raise HTTPException(
            status_code=500,
            detail="Unable to store GSC search performance.",
        ) from error

    return {
        "site_url": site_url,
        "rows": rows,
        "record_id": str(insert_result.inserted_id),
    }