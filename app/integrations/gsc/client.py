
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly"
]

def get_gsc_client(credentials_path: str):
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    return build(
        "searchconsole",
        "v1",
        credentials=credentials
    )

# service = get_gsc_client("app/integrations/gsc/credentials/service-account.json")

# sites = service.sites().list().execute()

# print(sites)
