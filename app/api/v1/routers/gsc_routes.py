import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.integrations.gsc.client import get_gsc_client
from app.integrations.gsc.service import get_search_performance, get_gsc_sites
from app.requestModels.req_models import GSCSearchRequest

logger = logging.getLogger(__name__)
gsc_router = APIRouter()


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
def fetch_gsc_search_performance(request: GSCSearchRequest):
    try:
        client = get_gsc_client(_credentials_path())
        rows = get_search_performance(
            service=client,
            site_url=request.site_url,
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
    return {"site_url": request.site_url, "rows": rows}