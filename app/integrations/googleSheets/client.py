from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]

def get_sheets_client(credentials_path: str):

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    return build(
        "sheets",
        "v4",
        credentials=credentials
    )