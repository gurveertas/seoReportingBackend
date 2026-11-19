
from googleapiclient.discovery import build

from app.integrations.service_account import get_service_account_credentials

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly"
]

def get_gsc_client(credentials_path: str | None = None):
    credentials = get_service_account_credentials(
        credentials_path,
        "GSC_SERVICE_ACCOUNT_JSON",
        SCOPES,
    )
    return build(
        "searchconsole",
        "v1",
        credentials=credentials
    )

# service = get_gsc_client("app/integrations/gsc/credentials/service-account.json")

# sites = service.sites().list().execute()

# print(sites)
