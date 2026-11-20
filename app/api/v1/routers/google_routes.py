"""Connect Google accounts and turn their websites into reportable clients.

Flow:
1. GET  /integrations/google/connect      -> returns Google's consent URL
2. Google redirects to /integrations/google/callback (backend), which stores
   the encrypted refresh token, syncs the account's sites, then redirects to
   the frontend (FRONTEND_URL + return_to, default /sites).
3. GET  /integrations/google/sites         -> every site across all connections
4. POST /integrations/google/sites/import  -> create clients from chosen sites
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from app.api.v1.routers.client_routes import get_authenticated_workspace_id
from app.core.security import create_oauth_state, decrypt_secret, read_oauth_state
from app.database.connection import get_database
from app.integrations.discovery import SITES, sync_connection
from app.integrations.google_oauth import (
    CONNECTIONS,
    GoogleOAuthError,
    build_authorization_url,
    exchange_code,
    fetch_userinfo,
    get_connection,
    mark_connection_error,
    public_connection,
    revoke_token,
    save_connection,
)
from app.middlewares.protect_route import protect_route
from app.models.client import Client, GA4Integration, GSCIntegration, Integrations
from app.requestModels.req_models import SiteImportRequest

logger = logging.getLogger(__name__)
google_router = APIRouter()


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _safe_return_path(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/sites"


def _redirect_to_frontend(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{_frontend_url()}{path}{query}", status_code=status.HTTP_303_SEE_OTHER)


def _session_workspace(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=[os.getenv("JWT_ALG", "HS256")])
    except jwt.InvalidTokenError:
        return None
    return payload.get("workspace_id") or payload.get("id")


@google_router.get("/connect")
def start_google_connect(
    return_to: str | None = Query(default=None, max_length=200),
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    try:
        state = create_oauth_state(workspace_id, _safe_return_path(return_to))
        return {"auth_url": build_authorization_url(state)}
    except GoogleOAuthError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@google_router.get("/callback", include_in_schema=False)
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if not state:
        return _redirect_to_frontend("/sites", google="error", reason="missing_state")
    try:
        state_data = read_oauth_state(state)
    except jwt.InvalidTokenError:
        return _redirect_to_frontend("/sites", google="error", reason="expired")

    return_to = _safe_return_path(state_data.get("return_to"))
    if error:
        reason = "denied" if error == "access_denied" else "google_error"
        return _redirect_to_frontend(return_to, google="error", reason=reason)
    if not code:
        return _redirect_to_frontend(return_to, google="error", reason="missing_code")

    # Bind the callback to the signed-in browser so a consent link created by
    # one workspace can't attach someone else's Google account to it.
    workspace_id = state_data.get("workspace_id")
    if not workspace_id or _session_workspace(request) != workspace_id:
        return _redirect_to_frontend(return_to, google="error", reason="session")

    try:
        tokens = exchange_code(code)
        profile = fetch_userinfo(tokens["access_token"])
        connection = save_connection(workspace_id, tokens, profile)
    except (GoogleOAuthError, KeyError) as exc:
        logger.warning("Google connect failed: %s", exc)
        return _redirect_to_frontend(return_to, google="error", reason="exchange")

    granted = set(connection.get("scopes") or [])
    if "https://www.googleapis.com/auth/webmasters.readonly" not in granted:
        return _redirect_to_frontend(return_to, google="error", reason="scopes")

    try:
        sync_connection(connection)
    except Exception as exc:  # Connected fine; listing can be retried from the UI.
        logger.exception("Initial site sync failed")
        mark_connection_error(connection["_id"], f"Site sync failed: {exc.__class__.__name__}")

    return _redirect_to_frontend(return_to, google="connected", email=connection.get("email") or "")


@google_router.get("/connections")
def list_connections(user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    connections = get_database()[CONNECTIONS].find({"workspace_id": workspace_id}).sort("created_at", 1)
    return {"connections": [public_connection(connection) for connection in connections]}


@google_router.post("/connections/{connection_id}/sync")
def sync_one_connection(connection_id: str, user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    connection = get_connection(workspace_id, connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Google connection not found.")
    try:
        result = sync_connection(connection)
    except Exception as error:
        logger.exception("Site sync failed")
        message = "Google refused access. Reconnect this account." if "invalid_grant" in str(error) else "Unable to list websites for this Google account."
        mark_connection_error(connection["_id"], message)
        raise HTTPException(status_code=502, detail=message) from error
    return {"status": True, **result}


@google_router.delete("/connections/{connection_id}")
def delete_connection(connection_id: str, user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    connection = get_connection(workspace_id, connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Google connection not found.")
    if connection.get("refresh_token_enc"):
        try:
            revoke_token(decrypt_secret(connection["refresh_token_enc"]))
        except Exception:
            logger.warning("Could not revoke Google token for %s", connection_id)
    database = get_database()
    database[SITES].delete_many({"workspace_id": workspace_id, "connection_id": connection_id})
    database[CONNECTIONS].delete_one({"_id": connection["_id"]})
    linked = database["clients"].count_documents(
        {"workspace_id": workspace_id, "google_connection_id": connection_id}
    )
    return {"status": True, "linked_clients": linked}


def _clients_by_site(workspace_id: str) -> dict[str, dict[str, Any]]:
    clients = get_database()["clients"].find(
        {"workspace_id": workspace_id, "integrations.gsc.property_url": {"$exists": True}},
        {"name": 1, "integrations.gsc.property_url": 1},
    )
    return {
        client["integrations"]["gsc"]["property_url"]: client
        for client in clients
        if (client.get("integrations") or {}).get("gsc")
    }


@google_router.get("/sites")
def list_sites(user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    database = get_database()
    connections = {
        str(connection["_id"]): connection
        for connection in database[CONNECTIONS].find({"workspace_id": workspace_id})
    }
    existing = _clients_by_site(workspace_id)
    sites = []
    for site in database[SITES].find({"workspace_id": workspace_id}).sort("display_name", 1):
        connection = connections.get(site["connection_id"])
        if not connection:
            continue
        client = existing.get(site["site_url"])
        sites.append(
            {
                "site_id": str(site["_id"]),
                "site_url": site["site_url"],
                "display_name": site.get("display_name"),
                "permission_level": site.get("permission_level"),
                "property_type": "domain" if site["site_url"].startswith("sc-domain:") else "url_prefix",
                "connection_id": site["connection_id"],
                "connection_email": connection.get("email"),
                "ga4_suggestions": site.get("ga4_suggestions", []),
                "client_id": str(client["_id"]) if client else None,
                "client_name": client.get("name") if client else None,
            }
        )
    ga4_properties = {
        connection_id: [
            {k: prop.get(k) for k in ("property_id", "display_name", "account_name")}
            for prop in connection.get("ga4_properties", [])
        ]
        for connection_id, connection in connections.items()
    }
    return {
        "connections": [public_connection(connection) for connection in connections.values()],
        "sites": sites,
        "ga4_properties": ga4_properties,
    }


@google_router.post("/sites/import", status_code=status.HTTP_201_CREATED)
def import_sites(payload: SiteImportRequest, user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    database = get_database()
    existing = _clients_by_site(workspace_id)
    created, updated = [], []

    for item in payload.sites:
        if not ObjectId.is_valid(item.site_id):
            raise HTTPException(status_code=422, detail="Invalid site id.")
        site = database[SITES].find_one({"_id": ObjectId(item.site_id), "workspace_id": workspace_id})
        if not site:
            raise HTTPException(status_code=404, detail="A selected website was not found. Refresh the list.")
        connection = get_connection(workspace_id, site["connection_id"])
        if not connection:
            raise HTTPException(status_code=409, detail="The Google account for a selected website was disconnected.")

        ga4_id = (item.ga4_property_id or "").strip() or None
        if ga4_id:
            allowed = {prop["property_id"] for prop in connection.get("ga4_properties", [])}
            if ga4_id not in allowed:
                raise HTTPException(status_code=422, detail=f"GA4 property {ga4_id} is not available in {connection.get('email')}.")

        integrations = Integrations(
            gsc=GSCIntegration(enabled=True, property_url=site["site_url"]),
            ga4=GA4Integration(enabled=True, property_id=ga4_id) if ga4_id else None,
        )
        name = (item.name or "").strip() or site.get("display_name") or site["site_url"]
        current = existing.get(site["site_url"])
        if current:
            # Re-link an existing client (e.g. after reconnecting the account).
            database["clients"].update_one(
                {"_id": current["_id"]},
                {
                    "$set": {
                        "google_connection_id": site["connection_id"],
                        "integrations.gsc": integrations.gsc.model_dump(),
                        **({"integrations.ga4": integrations.ga4.model_dump()} if integrations.ga4 else {}),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            updated.append(str(current["_id"]))
            continue

        client = Client(
            workspace_id=workspace_id,
            name=name[:120],
            integrations=integrations,
            google_connection_id=site["connection_id"],
            auto_monthly=payload.auto_monthly,
        )
        result = database["clients"].insert_one(client.model_dump())
        created.append(str(result.inserted_id))
        existing[site["site_url"]] = {"_id": result.inserted_id, "name": client.name}

    return {"status": True, "created": created, "updated": updated}
