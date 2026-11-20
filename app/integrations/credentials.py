"""Pick the right Google credentials for a client.

Clients imported from a connected Google account carry `google_connection_id`
and use that account's OAuth token. Older clients without it keep using the
service-account key files, so existing setups continue to work.
"""

from typing import Any, Literal

from fastapi import HTTPException, status

from app.integrations.google_oauth import (
    GoogleOAuthError,
    credentials_for_connection,
    get_connection,
)

Source = Literal["gsc", "ga4", "google_sheets"]


def user_credentials_for_client(client: dict[str, Any]):
    """Return OAuth credentials for the client's connected Google account,
    or None if the client is not linked to one (service-account fallback)."""
    connection_id = client.get("google_connection_id")
    if not connection_id:
        return None
    connection = get_connection(client["workspace_id"], connection_id)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Google account linked to this website was disconnected. Reconnect it in Settings.",
        )
    try:
        return credentials_for_connection(connection)
    except GoogleOAuthError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


def build_source_client(client: dict[str, Any], source: Source, credentials_path: str | None):
    credentials = user_credentials_for_client(client)
    if source == "gsc":
        from app.integrations.gsc.client import get_gsc_client

        return get_gsc_client(credentials_path, credentials=credentials)
    if source == "ga4":
        from app.integrations.ga4.client import get_ga4_client

        return get_ga4_client(credentials_path, credentials=credentials)
    from app.integrations.googleSheets.client import get_sheets_client

    return get_sheets_client(credentials_path, credentials=credentials)
