from googleapiclient.discovery import build

from app.integrations.service_account import get_service_account_credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]


def get_sheets_client(credentials_path: str | None = None, credentials=None):
    """Sheets client. Pass `credentials` (a connected Google account)
    or fall back to the service account."""
    if credentials is None:
        credentials = get_service_account_credentials(
            credentials_path,
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON",
            SCOPES,
        )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)
