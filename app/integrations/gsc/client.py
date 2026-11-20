from googleapiclient.discovery import build

from app.integrations.service_account import get_service_account_credentials

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly"
]


def get_gsc_client(credentials_path: str | None = None, credentials=None):
    """Search Console client. Pass `credentials` (a connected Google account)
    or fall back to the service account."""
    if credentials is None:
        credentials = get_service_account_credentials(
            credentials_path,
            "GSC_SERVICE_ACCOUNT_JSON",
            SCOPES,
        )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
