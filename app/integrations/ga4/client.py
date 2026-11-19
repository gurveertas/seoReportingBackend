from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly"
]

def get_ga4_client(credentials_path: str):

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    return BetaAnalyticsDataClient(
        credentials=credentials
    )