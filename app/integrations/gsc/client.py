from googleapiclient.discovery import build

def get_gsc_client(*, credentials):
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
