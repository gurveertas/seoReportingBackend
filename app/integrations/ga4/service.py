from typing import Optional, List

from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)


def get_ga4_report(
    client,
    property_id: str,
    start_date: str,
    end_date: str,
    dimensions: Optional[List[str]] = None,
    metrics: Optional[List[str]] = None,
):
    if metrics is None:
        metrics = [
            "totalUsers",
            "sessions",
            "screenPageViews",
        ]

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[
            DateRange(
                start_date=start_date,
                end_date=end_date,
            )
        ],
        dimensions=[
            Dimension(name=d) for d in (dimensions or [])
        ],
        metrics=[
            Metric(name=m) for m in metrics
        ],
    )

    response = client.run_report(request)

    return response