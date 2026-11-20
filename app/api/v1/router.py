from fastapi import APIRouter
from app.api.v1.routers.analytics_routes import analytics_router
from app.api.v1.routers.client_routes import client_router
from app.api.v1.routers.ga4_routes import ga4_router
from app.api.v1.routers.google_sheets_routes import google_sheets_router
from app.api.v1.routers.gsc_routes import gsc_router
from app.api.v1.routers.reports_routes import reports_router, workspace_reports_router
from app.api.v1.routers.google_routes import google_router
from app.api.v1.routers.cron_routes import cron_router

api_router = APIRouter()


@api_router.get("/health", tags=["Health"])
def get_api_health():
    return {"status": True, "message": "API is healthy"}


api_router.include_router(
    gsc_router,
    prefix="/clients/{client_id}/gsc",
    tags=["GSC"],
)
api_router.include_router(
    ga4_router,
    prefix="/clients/{client_id}/ga4",
    tags=["GA4"],
)
api_router.include_router(
    google_sheets_router,
    prefix="/clients/{client_id}/google-sheets",
    tags=["Google Sheets"],
)
api_router.include_router(
    analytics_router,
    prefix="/clients/{client_id}/analytics",
    tags=["Analytics"],
)
api_router.include_router(
    reports_router,
    prefix="/clients/{client_id}/reports",
    tags=["Reports"],
)
api_router.include_router(client_router, tags=["Clients"])
api_router.include_router(google_router, prefix="/integrations/google", tags=["Google accounts"])
api_router.include_router(workspace_reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(cron_router, prefix="/internal/cron")
