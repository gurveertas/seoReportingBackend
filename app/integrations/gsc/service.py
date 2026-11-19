
from typing import List, Optional


def get_search_performance(
    service,
    site_url,
    start_date,
    end_date,
    dimensions: Optional[List[str]] = None,
):
    request = {
        "startDate": start_date,
        "endDate": end_date,
        "rowLimit": 25000
    }
    if dimensions is not None:
        request["dimensions"] = dimensions

    response = (
        service.searchanalytics()
        .query(
            siteUrl=site_url,
            body=request
        )
        .execute()
    )

    return response.get("rows", [])

def get_gsc_sites(service):
    response = service.sites().list().execute()

    return response.get("siteEntry", [])


