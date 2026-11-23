import os
import re
import unittest
from unittest.mock import patch

import jwt
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import app


class ReportsRouteTests(unittest.TestCase):
    def test_monthly_and_weekly_routes_return_database_backed_pdfs(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        workspace_id = str(ObjectId())
        client_id = str(ObjectId())
        token = jwt.encode(
            {
                "id": workspace_id,
                "workspace_id": workspace_id,
                "username": "test-user",
                "fullname": "Test User",
            },
            secret,
            algorithm="HS256",
        )
        dashboard = {
            "client": {"client_id": client_id, "name": "Test Client"},
            "period": {
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
                "comparison_start_date": "2026-09-01",
                "comparison_end_date": "2026-09-30",
            },
            "sources": {"gsc": {"site_url": "https://example.com/"}},
            "kpis": [
                {
                    "label": "Search clicks",
                    "value": 20,
                    "change": 5.0,
                    "change_unit": "percent",
                    "trend": "up",
                }
            ],
            "charts": {
                "gsc_daily": {
                    "labels": ["2026-10-01", "2026-10-02"],
                    "datasets": [{"label": "Clicks", "data": [5, 15]}],
                }
            },
            "tables": {
                "gsc_daily": {
                    "columns": ["date", "clicks"],
                    "rows": [{"date": "2026-10-01", "clicks": 5}],
                },
                "top_queries": {"columns": ["query", "clicks"], "rows": []},
                "top_pages": {"columns": ["page", "clicks"], "rows": []},
                "ga4_daily": {"columns": ["date", "sessions"], "rows": []},
                "google_sheets": {"columns": [], "rows": []},
            },
        }

        with patch.dict(
            os.environ,
            {"JWT_SECRET": secret, "JWT_ALG": "HS256"},
        ):
            with TestClient(app) as client:
                for period in ("monthly", "weekly"):
                    with self.subTest(period=period):
                        with patch(
                            "app.api.v1.routers.reports_routes._dashboard_from_database",
                            return_value=dashboard,
                        ) as get_dashboard:
                            response = client.get(
                                f"/api/v1/clients/{client_id}/reports/{period}",
                                headers={"Authorization": f"Bearer {token}"},
                            )

                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.headers["content-type"], "application/pdf")
                        self.assertTrue(response.content.startswith(b"%PDF-"))
                        self.assertEqual(len(re.findall(rb"/Type /Page\b", response.content)), 1)
                        self.assertIn(
                            f"seo-report-{period}-2026-10-01-2026-10-31.pdf",
                            response.headers["content-disposition"],
                        )
                        get_dashboard.assert_called_once_with(
                            workspace_id,
                            client_id,
                            period,
                        )

    def test_report_can_render_when_no_integration_data_is_stored(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        workspace_id = str(ObjectId())
        client_id = str(ObjectId())
        empty_dashboard = {
            "client": {"client_id": client_id, "name": "Test Client"},
            "period": {},
            "sources": {},
            "kpis": [],
            "charts": {
                "gsc_daily": {
                    "labels": [],
                    "datasets": [{"label": "Clicks", "data": []}],
                },
            },
            "tables": {},
        }
        token = jwt.encode(
            {
                "id": workspace_id,
                "workspace_id": workspace_id,
                "username": "test-user",
            },
            secret,
            algorithm="HS256",
        )

        with patch.dict(
            os.environ,
            {"JWT_SECRET": secret, "JWT_ALG": "HS256"},
        ):
            with TestClient(app) as client:
                with patch(
                    "app.api.v1.routers.reports_routes._dashboard_from_database",
                    return_value=empty_dashboard,
                ):
                    response = client.get(
                        f"/api/v1/clients/{client_id}/reports/weekly",
                        headers={"Authorization": f"Bearer {token}"},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(len(re.findall(rb"/Type /Page\b", response.content)), 1)
