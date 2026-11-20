import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.api.v1.routers.analytics_routes import (
    _authenticated_workspace_id,
    _dashboard_from_database,
    _period_bounds,
    refresh_analytics,
)


class AnalyticsRouteTests(unittest.TestCase):
    def test_monthly_period_uses_latest_complete_month_and_previous_month(self):
        bounds = _period_bounds("monthly", today=date(2026, 11, 19))

        self.assertEqual(
            bounds,
            (
                date(2026, 10, 1),
                date(2026, 10, 31),
                date(2026, 9, 1),
                date(2026, 9, 30),
            ),
        )

    def test_weekly_period_uses_latest_complete_monday_to_sunday(self):
        bounds = _period_bounds("weekly", today=date(2026, 11, 19))

        self.assertEqual(
            bounds,
            (
                date(2026, 11, 9),
                date(2026, 11, 15),
                date(2026, 11, 2),
                date(2026, 11, 8),
            ),
        )

    def test_rejects_analytics_token_without_a_valid_workspace_id(self):
        with self.assertRaises(HTTPException) as error:
            _authenticated_workspace_id({"workspace_id": "invalid"})

        self.assertEqual(error.exception.status_code, 401)

    @patch("app.api.v1.routers.analytics_routes.get_workspace_client")
    @patch("app.api.v1.routers.analytics_routes._period_bounds")
    @patch("app.api.v1.routers.analytics_routes.get_database")
    def test_dashboard_returns_no_data_status_from_database(
        self,
        get_database,
        period_bounds,
        get_workspace_client,
    ):
        period_bounds.return_value = (
            date(2026, 10, 1),
            date(2026, 10, 31),
            date(2026, 9, 1),
            date(2026, 9, 30),
        )
        database = MagicMock()
        database.__getitem__.return_value.find_one.return_value = None
        get_database.return_value = database
        get_workspace_client.return_value = {
            "name": "Example Client",
        }

        result = _dashboard_from_database(
            "workspace-id",
            "client-id",
            "monthly",
        )

        self.assertEqual(result["client"]["name"], "Example Client")
        self.assertEqual(result["period"]["mode"], "monthly")
        self.assertEqual(result["sources"]["gsc"]["status"], "no_data")
        self.assertEqual(result["sources"]["ga4"]["status"], "no_data")
        self.assertEqual(
            result["sources"]["google_sheets"]["status"],
            "no_data",
        )
        self.assertEqual(result["charts"]["gsc_daily"]["labels"], [])
        self.assertEqual(result["tables"]["top_queries"]["rows"], [])
        get_database.assert_called()

    @patch("app.api.v1.routers.analytics_routes.get_workspace_client")
    @patch("app.api.v1.routers.analytics_routes._find_latest")
    @patch("app.api.v1.routers.analytics_routes._period_bounds")
    def test_dashboard_formats_stored_snapshots_for_kpis_charts_and_tables(
        self,
        period_bounds,
        find_latest,
        get_workspace_client,
    ):
        current_start = date(2026, 10, 1)
        current_end = date(2026, 10, 31)
        previous_start = date(2026, 9, 1)
        previous_end = date(2026, 9, 30)
        period_bounds.return_value = (
            current_start,
            current_end,
            previous_start,
            previous_end,
        )
        snapshots = {
            ("ga4_reports", (), current_start.isoformat()): {
                "rows": [
                    {
                        "metrics": {
                            "totalUsers": "12",
                            "sessions": "20",
                            "screenPageViews": "40",
                        }
                    }
                ]
            },
            ("ga4_reports", (), previous_start.isoformat()): {
                "rows": [
                    {
                        "metrics": {
                            "totalUsers": "10",
                            "sessions": "18",
                            "screenPageViews": "32",
                        }
                    }
                ]
            },
            ("ga4_reports", ("date",), current_start.isoformat()): {
                "rows": [
                    {
                        "dimensions": {"date": "20261001"},
                        "metrics": {"totalUsers": "12", "sessions": "20", "screenPageViews": "40"},
                    }
                ]
            },
            ("gsc_search_reports", (), current_start.isoformat()): {
                "rows": [
                    {
                        "clicks": 10,
                        "impressions": 100,
                        "ctr": 0.1,
                        "position": 5.0,
                    }
                ]
            },
            ("gsc_search_reports", (), previous_start.isoformat()): {
                "rows": [
                    {
                        "clicks": 5,
                        "impressions": 50,
                        "ctr": 0.08,
                        "position": 6.5,
                    }
                ]
            },
            ("gsc_search_reports", ("date",), current_start.isoformat()): {
                "rows": [
                    {
                        "keys": ["2026-10-01"],
                        "clicks": 10,
                        "impressions": 100,
                        "ctr": 0.1,
                        "position": 5.0,
                    }
                ]
            },
            ("gsc_search_reports", ("query",), current_start.isoformat()): {
                "rows": [
                    {
                        "keys": ["best product"],
                        "clicks": 10,
                        "impressions": 100,
                        "ctr": 0.1,
                        "position": 5.0,
                    }
                ]
            },
            ("gsc_search_reports", ("page",), current_start.isoformat()): None,
            ("google_sheets_reports", (), None): {
                "values": [["Leads", "Month"], [4, "October"]],
            },
        }

        def find_snapshot(collection, query):
            dimensions = query.get("dimension_headers", query.get("dimensions", []))
            key = (
                collection,
                tuple(dimensions),
                query.get("start_date"),
            )
            return snapshots.get(key)

        find_latest.side_effect = find_snapshot
        get_workspace_client.return_value = {"name": "Example Client"}
        result = _dashboard_from_database(
            "workspace-id",
            "client-id",
            "monthly",
        )

        self.assertTrue(
            all(
                args[1].get("workspace_id") == "workspace-id"
                and args[1].get("client_id") == "client-id"
                for args, _ in find_latest.call_args_list
            )
        )
        self.assertEqual(result["kpis"][0]["change"], 100)
        self.assertEqual(result["kpis"][2]["value"], 10)
        self.assertEqual(result["kpis"][3]["trend"], "up")
        self.assertEqual(result["charts"]["ga4_daily"]["labels"], ["2026-10-01"])
        self.assertEqual(
            result["tables"]["top_queries"]["rows"][0]["query"],
            "best product",
        )
        self.assertEqual(
            result["tables"]["google_sheets"]["columns"],
            ["Leads", "Month"],
        )

    @patch("app.api.v1.routers.analytics_routes._dashboard_from_database")
    @patch("app.api.v1.routers.analytics_routes._refresh_sheets")
    @patch("app.api.v1.routers.analytics_routes._refresh_gsc")
    @patch("app.api.v1.routers.analytics_routes._refresh_ga4")
    @patch("app.api.v1.routers.analytics_routes._period_bounds")
    def test_refresh_rebuilds_dashboard_after_refreshing_sources(
        self,
        period_bounds,
        refresh_ga4,
        refresh_gsc,
        refresh_sheets,
        dashboard_from_database,
    ):
        period_bounds.return_value = (
            date(2026, 10, 1),
            date(2026, 10, 31),
            date(2026, 9, 1),
            date(2026, 9, 30),
        )
        events = []
        refresh_ga4.side_effect = lambda *args: events.append("ga4") or ["ga4-id"]
        refresh_gsc.side_effect = lambda *args: events.append("gsc") or ["gsc-id"]
        refresh_sheets.side_effect = (
            lambda *args: events.append("google_sheets") or "sheets-id"
        )
        dashboard_from_database.side_effect = (
            lambda *args: events.append("database") or {"period": {}}
        )

        workspace_id = str(ObjectId())
        client_id = str(ObjectId())
        result = refresh_analytics(
            client_id=client_id,
            period="monthly",
            user={"workspace_id": workspace_id},
        )

        self.assertEqual(events, ["ga4", "gsc", "google_sheets", "database"])
        self.assertEqual(result["refresh"]["ga4"]["status"], "refreshed")
        self.assertEqual(result["refresh"]["gsc"]["status"], "refreshed")
        self.assertEqual(
            result["refresh"]["google_sheets"]["status"],
            "refreshed",
        )
        dashboard_from_database.assert_called_once_with(
            workspace_id,
            client_id,
            "monthly",
        )


if __name__ == "__main__":
    unittest.main()
