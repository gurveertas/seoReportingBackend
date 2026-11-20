"""Google OAuth 2.0 (web server flow) for connecting a user's own Google account.

The user grants read-only access to Search Console, Analytics and Sheets. We keep
only the refresh token (encrypted) and mint short-lived access tokens on demand.
"""

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from bson import ObjectId
from google.oauth2.credentials import Credentials

from app.core.security import decrypt_secret, encrypt_secret
from app.database.connection import get_database

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

CONNECTIONS = "google_connections"


class GoogleOAuthError(RuntimeError):
    pass


def oauth_settings() -> dict[str, str]:
    settings = {
        "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("GOOGLE_OAUTH_REDIRECT_URI", ""),
    }
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise GoogleOAuthError(
            "Google sign-in is not configured on the server (missing "
            + ", ".join(f"GOOGLE_OAUTH_{name.upper()}" for name in missing)
            + ")."
        )
    return settings


def build_authorization_url(state: str, login_hint: str | None = None) -> str:
    settings = oauth_settings()
    params = {
        "client_id": settings["client_id"],
        "redirect_uri": settings["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # "consent" guarantees Google returns a refresh token every time,
        # "select_account" lets agencies pick which of their Google accounts to add.
        "prompt": "consent select_account",
        "include_granted_scopes": "true",
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    settings = oauth_settings()
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings["client_id"],
            "client_secret": settings["client_secret"],
            "redirect_uri": settings["redirect_uri"],
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise GoogleOAuthError(f"Google rejected the authorization code ({response.status_code}).")
    return response.json()


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    response = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if response.status_code != 200:
        raise GoogleOAuthError("Unable to read the Google account profile.")
    return response.json()


def revoke_token(token: str) -> None:
    try:
        requests.post(REVOKE_URL, params={"token": token}, timeout=10)
    except requests.RequestException:
        pass  # Best effort: the stored token is deleted either way.


def save_connection(workspace_id: str, tokens: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Create or update the connection for this Google account in this workspace."""
    collection = get_database()[CONNECTIONS]
    collection.create_index([("workspace_id", 1), ("google_sub", 1)], unique=True)
    now = datetime.now(timezone.utc)
    update: dict[str, Any] = {
        "workspace_id": workspace_id,
        "google_sub": profile["sub"],
        "email": profile.get("email"),
        "name": profile.get("name"),
        "picture": profile.get("picture"),
        "scopes": (tokens.get("scope") or "").split(),
        "status": "active",
        "last_error": None,
        "updated_at": now,
    }
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        update["refresh_token_enc"] = encrypt_secret(refresh_token)

    existing = collection.find_one({"workspace_id": workspace_id, "google_sub": profile["sub"]})
    if not existing and not refresh_token:
        raise GoogleOAuthError("Google did not return a refresh token. Please try connecting again.")

    collection.update_one(
        {"workspace_id": workspace_id, "google_sub": profile["sub"]},
        {"$set": update, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return collection.find_one({"workspace_id": workspace_id, "google_sub": profile["sub"]})


def get_connection(workspace_id: str, connection_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(connection_id):
        return None
    return get_database()[CONNECTIONS].find_one(
        {"_id": ObjectId(connection_id), "workspace_id": workspace_id}
    )


def mark_connection_error(connection_id: Any, message: str) -> None:
    get_database()[CONNECTIONS].update_one(
        {"_id": connection_id},
        {"$set": {"status": "error", "last_error": message, "updated_at": datetime.now(timezone.utc)}},
    )


def credentials_for_connection(connection: dict[str, Any]) -> Credentials:
    settings = oauth_settings()
    if not connection.get("refresh_token_enc"):
        raise GoogleOAuthError("This Google connection has no stored token. Reconnect the account.")
    return Credentials(
        token=None,
        refresh_token=decrypt_secret(connection["refresh_token_enc"]),
        token_uri=TOKEN_URL,
        client_id=settings["client_id"],
        client_secret=settings["client_secret"],
        scopes=connection.get("scopes") or SCOPES,
    )


def public_connection(connection: dict[str, Any]) -> dict[str, Any]:
    return {
        "connection_id": str(connection["_id"]),
        "email": connection.get("email"),
        "name": connection.get("name"),
        "picture": connection.get("picture"),
        "status": connection.get("status", "active"),
        "last_error": connection.get("last_error"),
        "sites_synced_at": connection.get("sites_synced_at"),
        "created_at": connection.get("created_at"),
        "updated_at": connection.get("updated_at"),
    }
