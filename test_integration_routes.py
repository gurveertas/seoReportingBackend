import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.routers.ga4_routes import fetch_ga4_report
from app.api.v1.routers.google_sheets_routes import fetch_sheet_values
from app.api.v1.routers.gsc_routes import (
    fetch_gsc_search_performance,
    fetch_gsc_sites,
)
from app.requestModels.req_models import (
    GA4ReportRequest,
    GSCSearchRequest,
    SheetsDataRequest,
)


class IntegrationRouteTests(unittest.TestCase):
    @patch("app.api.v1.routers.ga4_routes.get_ga4_report")
    @patch("app.api.v1.routers.ga4_routes.get_ga4_client")
    def test_ga4_report_returns_json_friendly_rows(self, get_client, get_report):
        get_report.return_value = SimpleNamespace(
            dimension_headers=[SimpleNamespace(name="date")],
            metric_headers=[SimpleNamespace(name="sessions")],
            row_count=1,
            rows=[
                SimpleNamespace(
                    dimension_values=[SimpleNamespace(value="20261118")],
                    metric_values=[SimpleNamespace(value="12")],
                )
            ],
        )

        result = fetch_ga4_report(
            GA4ReportRequest(
                property_id="property-1",
                start_date="7daysAgo",
                end_date="yesterday",
                dimensions=["date"],
                metrics=["sessions"],
            )
        )

        self.assertEqual(
            result["rows"],
            [{"dimensions": {"date": "20261118"}, "metrics": {"sessions": "12"}}],
        )
        get_report.assert_called_once()

    @patch("app.api.v1.routers.google_sheets_routes.get_sheet_data")
    @patch("app.api.v1.routers.google_sheets_routes.get_sheets_client")
    def test_sheets_values_returns_data(self, get_client, get_data):
        get_data.return_value = [["name"], ["value"]]

        result = fetch_sheet_values(
            SheetsDataRequest(spreadsheet_id="sheet-1", range_name="Tab!A1:B2")
        )

        self.assertEqual(result["values"], [["name"], ["value"]])
        get_data.assert_called_once_with(
            service=get_client.return_value,
            spreadsheet_id="sheet-1",
            range_name="Tab!A1:B2",
        )

    @patch("app.api.v1.routers.gsc_routes.get_gsc_sites")
    @patch("app.api.v1.routers.gsc_routes.get_gsc_client")
    def test_gsc_sites_returns_accessible_sites(self, get_client, get_sites):
        get_sites.return_value = [{"siteUrl": "https://example.com/"}]

        result = fetch_gsc_sites()

        self.assertEqual(result["sites"], [{"siteUrl": "https://example.com/"}])
        get_sites.assert_called_once_with(get_client.return_value)

    @patch("app.api.v1.routers.gsc_routes.get_search_performance")
    @patch("app.api.v1.routers.gsc_routes.get_gsc_client")
    def test_gsc_search_performance_forwards_request(self, get_client, get_data):
        get_data.return_value = [{"clicks": 2}]

        result = fetch_gsc_search_performance(
            GSCSearchRequest(
                site_url="https://example.com/",
                start_date="2026-11-01",
                end_date="2026-11-18",
                dimensions=["query"],
            )
        )

        self.assertEqual(result["rows"], [{"clicks": 2}])
        get_data.assert_called_once_with(
            service=get_client.return_value,
            site_url="https://example.com/",
            start_date="2026-11-01",
            end_date="2026-11-18",
            dimensions=["query"],
        )


if __name__ == "__main__":
    unittest.main()
