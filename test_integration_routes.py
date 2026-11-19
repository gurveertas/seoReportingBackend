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
    @patch("app.api.v1.routers.ga4_routes.get_user_integration_property")
    @patch("app.api.v1.routers.ga4_routes.get_database")
    def test_ga4_report_returns_json_friendly_rows(
        self,
        get_database,
        get_integration_property,
        get_client,
        get_report,
    ):
        get_integration_property.return_value = "db-property-1"
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
                start_date="7daysAgo",
                end_date="yesterday",
                dimensions=["date"],
                metrics=["sessions"],
            ),
            user={"id": "authenticated-user-id"},
        )

        self.assertEqual(
            result["rows"],
            [{"dimensions": {"date": "20261118"}, "metrics": {"sessions": "12"}}],
        )
        self.assertEqual(result["record_id"], str(
            get_database.return_value["ga4_reports"].insert_one.return_value.inserted_id
        ))
        get_report.assert_called_once_with(
            client=get_client.return_value,
            property_id="db-property-1",
            start_date="7daysAgo",
            end_date="yesterday",
            dimensions=["date"],
            metrics=["sessions"],
        )
        get_integration_property.assert_called_once_with(
            "authenticated-user-id",
            "ga4",
            "property_id",
        )
        stored_record = (
            get_database.return_value["ga4_reports"].insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["user_id"], "authenticated-user-id")
        self.assertEqual(stored_record["property_id"], "db-property-1")
        self.assertEqual(stored_record["rows"], result["rows"])

    @patch("app.api.v1.routers.google_sheets_routes.get_sheet_data")
    @patch("app.api.v1.routers.google_sheets_routes.get_sheets_client")
    @patch(
        "app.api.v1.routers.google_sheets_routes.get_user_integration_property"
    )
    @patch("app.api.v1.routers.google_sheets_routes.get_database")
    def test_sheets_values_returns_data(
        self,
        get_database,
        get_integration_property,
        get_client,
        get_data,
    ):
        get_integration_property.return_value = "db-sheet-1"
        get_data.return_value = [["name"], ["value"]]

        result = fetch_sheet_values(
            SheetsDataRequest(range_name="Tab!A1:B2"),
            user={"id": "authenticated-user-id"},
        )

        self.assertEqual(result["spreadsheet_id"], "db-sheet-1")
        self.assertEqual(result["values"], [["name"], ["value"]])
        stored_record = (
            get_database.return_value["google_sheets_reports"]
            .insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["user_id"], "authenticated-user-id")
        self.assertEqual(stored_record["spreadsheet_id"], "db-sheet-1")
        self.assertEqual(stored_record["values"], result["values"])
        get_data.assert_called_once_with(
            service=get_client.return_value,
            spreadsheet_id="db-sheet-1",
            range_name="Tab!A1:B2",
        )
        get_integration_property.assert_called_once_with(
            "authenticated-user-id",
            "google_sheets",
            "property_id",
        )

    @patch("app.api.v1.routers.gsc_routes.get_gsc_sites")
    @patch("app.api.v1.routers.gsc_routes.get_gsc_client")
    @patch("app.api.v1.routers.gsc_routes.get_database")
    def test_gsc_sites_returns_accessible_sites(
        self,
        get_database,
        get_client,
        get_sites,
    ):
        get_sites.return_value = [{"siteUrl": "https://example.com/"}]

        result = fetch_gsc_sites(user={"id": "authenticated-user-id"})

        self.assertEqual(result["sites"], [{"siteUrl": "https://example.com/"}])
        stored_record = (
            get_database.return_value["gsc_sites"].insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["user_id"], "authenticated-user-id")
        self.assertEqual(stored_record["sites"], result["sites"])
        get_sites.assert_called_once_with(get_client.return_value)

    @patch("app.api.v1.routers.gsc_routes.get_search_performance")
    @patch("app.api.v1.routers.gsc_routes.get_gsc_client")
    @patch("app.api.v1.routers.gsc_routes.get_user_integration_property")
    @patch("app.api.v1.routers.gsc_routes.get_database")
    def test_gsc_search_performance_forwards_request(
        self,
        get_database,
        get_integration_property,
        get_client,
        get_data,
    ):
        get_integration_property.return_value = "https://db-example.com/"
        get_data.return_value = [{"clicks": 2}]

        result = fetch_gsc_search_performance(
            GSCSearchRequest(
                start_date="2026-11-01",
                end_date="2026-11-18",
                dimensions=["query"],
            ),
            user={"id": "authenticated-user-id"},
        )

        self.assertEqual(result["site_url"], "https://db-example.com/")
        self.assertEqual(result["rows"], [{"clicks": 2}])
        stored_record = (
            get_database.return_value["gsc_search_reports"]
            .insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["user_id"], "authenticated-user-id")
        self.assertEqual(stored_record["site_url"], result["site_url"])
        self.assertEqual(stored_record["rows"], result["rows"])
        get_data.assert_called_once_with(
            service=get_client.return_value,
            site_url="https://db-example.com/",
            start_date="2026-11-01",
            end_date="2026-11-18",
            dimensions=["query"],
        )
        get_integration_property.assert_called_once_with(
            "authenticated-user-id",
            "gsc",
            "property_url",
        )


if __name__ == "__main__":
    unittest.main()
