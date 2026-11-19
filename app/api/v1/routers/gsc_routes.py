import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.integrations.gsc.client import get_gsc_client
from app.integrations.gsc.service import get_search_performance, get_gsc_sites
from app.api.v1.routers.client_routes import get_user_integration_property
from app.database.connection import get_database
from app.middlewares.protect_route import protect_route
from app.models.gsc import GSCDocument
from app.requestModels.req_models import GSCSearchRequest

logger = logging.getLogger(__name__)
gsc_router = APIRouter(dependencies=[Depends(protect_route)])


def save_gsc_data(data: GSCDocument):
    document = data.model_dump()
    return get_database().gsc_data.update_one(
        {
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
async def get_gsc_health():
    return {"status":True, "message":"GSC routes are healthy"}


@gsc_router.get("/sites")
def fetch_gsc_sites():
    try:
        client = get_gsc_client(_credentials_path())
        sites = get_gsc_sites(client)
    except Exception as error:
        logger.exception("GSC sites request failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve GSC sites.",
        ) from error
    return {"sites": sites}


@gsc_router.post("/search-performance")
def fetch_gsc_search_performance(
    request: GSCSearchRequest,
    user: dict[str, Any] = Depends(protect_route),
):
    site_url = get_user_integration_property(
        user.get("id"),
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
    return {"site_url": site_url, "rows": rows}