from google.analytics.data_v1beta import BetaAnalyticsDataClient

from app.integrations.service_account import get_service_account_credentials

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly"
]

def get_ga4_client(credentials_path: str | None = None):
    credentials = get_service_account_credentials(
        credentials_path,
        "GA4_SERVICE_ACCOUNT_JSON",
        SCOPES,
    )

    return BetaAnalyticsDataClient(
        credentials=credentials
    )