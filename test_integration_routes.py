import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId

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
    def setUp(self):
        self.workspace_id = str(ObjectId())
        self.client_id = str(ObjectId())
        self.user = {"workspace_id": self.workspace_id}
        for module in ("ga4_routes", "gsc_routes", "google_sheets_routes"):
            lookup = patch(f"app.api.v1.routers.{module}.get_workspace_client")
            lookup.start()
            self.addCleanup(lookup.stop)

    @patch("app.api.v1.routers.ga4_routes.get_ga4_report")
    @patch("app.api.v1.routers.ga4_routes.build_source_client")
    @patch("app.api.v1.routers.ga4_routes.get_client_integration_property")
    @patch("app.api.v1.routers.ga4_routes.get_database")
    def test_ga4_report_is_saved_with_workspace_and_client_scope(
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
            client_id=self.client_id,
            request=GA4ReportRequest(
                start_date="7daysAgo",
                end_date="yesterday",
                dimensions=["date"],
                metrics=["sessions"],
            ),
            user=self.user,
        )

        self.assertEqual(
            result["rows"],
            [{"dimensions": {"date": "20261118"}, "metrics": {"sessions": "12"}}],
        )
        get_report.assert_called_once_with(
            client=get_client.return_value,
            property_id="db-property-1",
            start_date="7daysAgo",
            end_date="yesterday",
            dimensions=["date"],
            metrics=["sessions"],
        )
        get_integration_property.assert_called_once_with(
            self.workspace_id,
            self.client_id,
            "ga4",
            "property_id",
        )
        stored_record = (
            get_database.return_value["ga4_reports"].insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["workspace_id"], self.workspace_id)
        self.assertEqual(stored_record["client_id"], self.client_id)
        self.assertEqual(stored_record["property_id"], "db-property-1")

    @patch("app.api.v1.routers.google_sheets_routes.get_sheet_data")
    @patch("app.api.v1.routers.google_sheets_routes.build_source_client")
    @patch(
        "app.api.v1.routers.google_sheets_routes.get_client_integration_property"
    )
    @patch("app.api.v1.routers.google_sheets_routes.get_database")
    def test_sheets_values_are_saved_with_workspace_and_client_scope(
        self,
        get_database,
        get_integration_property,
        get_client,
        get_data,
    ):
        get_integration_property.return_value = "db-sheet-1"
        get_data.return_value = [["name"], ["value"]]

        result = fetch_sheet_values(
            client_id=self.client_id,
            request=SheetsDataRequest(range_name="Tab!A1:B2"),
            user=self.user,
        )

        self.assertEqual(result["spreadsheet_id"], "db-sheet-1")
        self.assertEqual(result["values"], [["name"], ["value"]])
        stored_record = (
            get_database.return_value["google_sheets_reports"]
            .insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["workspace_id"], self.workspace_id)
        self.assertEqual(stored_record["client_id"], self.client_id)
        self.assertEqual(stored_record["spreadsheet_id"], "db-sheet-1")
        get_data.assert_called_once_with(
            service=get_client.return_value,
            spreadsheet_id="db-sheet-1",
            range_name="Tab!A1:B2",
        )
        get_integration_property.assert_called_once_with(
            self.workspace_id,
            self.client_id,
            "google_sheets",
            "property_id",
        )

    @patch("app.api.v1.routers.gsc_routes.get_workspace_client")
    @patch("app.api.v1.routers.gsc_routes.get_gsc_sites")
    @patch("app.api.v1.routers.gsc_routes.build_source_client")
    @patch("app.api.v1.routers.gsc_routes.get_database")
    def test_gsc_sites_are_saved_for_the_selected_client(
        self,
        get_database,
        get_client,
        get_sites,
        get_workspace_client,
    ):
        get_sites.return_value = [{"siteUrl": "https://example.com/"}]

        result = fetch_gsc_sites(client_id=self.client_id, user=self.user)

        self.assertEqual(result["sites"], [{"siteUrl": "https://example.com/"}])
        get_workspace_client.assert_called_once_with(
            self.workspace_id,
            self.client_id,
        )
        stored_record = (
            get_database.return_value["gsc_sites"].insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["workspace_id"], self.workspace_id)
        self.assertEqual(stored_record["client_id"], self.client_id)
        self.assertEqual(stored_record["sites"], result["sites"])
        get_sites.assert_called_once_with(get_client.return_value)

    @patch("app.api.v1.routers.gsc_routes.get_search_performance")
    @patch("app.api.v1.routers.gsc_routes.build_source_client")
    @patch("app.api.v1.routers.gsc_routes.get_client_integration_property")
    @patch("app.api.v1.routers.gsc_routes.get_database")
    def test_gsc_search_performance_is_scoped_to_the_selected_client(
        self,
        get_database,
        get_integration_property,
        get_client,
        get_data,
    ):
        get_integration_property.return_value = "https://db-example.com/"
        get_data.return_value = [{"clicks": 2}]

        result = fetch_gsc_search_performance(
            client_id=self.client_id,
            request=GSCSearchRequest(
                start_date="2026-11-01",
                end_date="2026-11-18",
                dimensions=["query"],
            ),
            user=self.user,
        )

        self.assertEqual(result["site_url"], "https://db-example.com/")
        self.assertEqual(result["rows"], [{"clicks": 2}])
        stored_record = (
            get_database.return_value["gsc_search_reports"]
            .insert_one.call_args.args[0]
        )
        self.assertEqual(stored_record["workspace_id"], self.workspace_id)
        self.assertEqual(stored_record["client_id"], self.client_id)
        self.assertEqual(stored_record["site_url"], result["site_url"])
        get_data.assert_called_once_with(
            service=get_client.return_value,
            site_url="https://db-example.com/",
            start_date="2026-11-01",
            end_date="2026-11-18",
            dimensions=["query"],
        )
        get_integration_property.assert_called_once_with(
            self.workspace_id,
            self.client_id,
            "gsc",
            "property_url",
        )


if __name__ == "__main__":
    unittest.main()
