from typing import Any, Literal

from fastapi import HTTPException, status

from app.integrations.google_oauth import (
    GoogleOAuthError,
    credentials_for_connection,
    get_connection,
)

Source = Literal["gsc", "ga4", "google_sheets"]


def user_credentials_for_client(client: dict[str, Any]):
    connection_id = client.get("google_connection_id")
    if not connection_id:
        raise HTTPException(409, "Connect a Google account and import this website before refreshing Google data.")
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


def build_source_client(client: dict[str, Any], source: Source):
    credentials = user_credentials_for_client(client)
    if source == "gsc":
        from app.integrations.gsc.client import get_gsc_client

        return get_gsc_client(credentials=credentials)
    if source == "ga4":
        from app.integrations.ga4.client import get_ga4_client

        return get_ga4_client(credentials=credentials)
    from app.integrations.googleSheets.client import get_sheets_client

    return get_sheets_client(credentials=credentials)
