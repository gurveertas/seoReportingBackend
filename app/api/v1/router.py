from fastapi import APIRouter
from app.api.v1.routers.client_routes import client_router
from app.api.v1.routers.ga4_routes import ga4_router
from app.api.v1.routers.google_sheets_routes import google_sheets_router
from app.api.v1.routers.gsc_routes import gsc_router

api_router = APIRouter()

api_router.include_router(gsc_router, prefix="/gsc", tags=["GSC"])
api_router.include_router(ga4_router, prefix="/ga4", tags=["GA4"])
api_router.include_router(
    google_sheets_router,
    prefix="/google-sheets",
    tags=["Google Sheets"],
)
api_router.include_router(client_router, tags=["Clients"])