from google.analytics.data_v1beta import BetaAnalyticsDataClient

def get_ga4_client(*, credentials):
    return BetaAnalyticsDataClient(credentials=credentials)
