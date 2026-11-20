import os
import unittest
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from app.main import app


class ProtectRouteTests(unittest.TestCase):
    integration_health_routes = (
        "/api/v1/gsc/health",
        "/api/v1/ga4/health",
        "/api/v1/google-sheets/health",
    )

    def test_frontend_health_route_is_public(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/health",
                headers={"Origin": "http://localhost:5174"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": True, "message": "API is healthy"},
        )
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5174",
        )

    def test_all_integration_routes_require_authentication(self):
        requests = (
            ("GET", "/api/v1/gsc/health", None),
            ("GET", "/api/v1/gsc/sites", None),
            (
                "POST",
                "/api/v1/gsc/search-performance",
                {
                    "site_url": "https://example.com/",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-18",
                    "dimensions": ["query"],
                },
            ),
            ("GET", "/api/v1/ga4/health", None),
            (
                "POST",
                "/api/v1/ga4/report",
                {
                    "property_id": "property-1",
                    "start_date": "7daysAgo",
                    "end_date": "yesterday",
                },
            ),
            ("GET", "/api/v1/google-sheets/health", None),
            ("GET", "/api/v1/analytics/monthly", None),
            ("GET", "/api/v1/analytics/weekly", None),
            ("GET", "/api/v1/reports/monthly", None),
            ("GET", "/api/v1/reports/weekly", None),
            ("POST", "/api/v1/analytics/refresh", None),
            (
                "POST",
                "/api/v1/google-sheets/values",
                {"spreadsheet_id": "sheet-1", "range_name": "Tab!A1:B2"},
            ),
        )

        with TestClient(app) as client:
            for method, path, body in requests:
                response = client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401, path)

    def test_each_integration_accepts_a_valid_bearer_token(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        token = jwt.encode({"username": "test-user"}, secret, algorithm="HS256")

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with TestClient(app) as client:
                for path in self.integration_health_routes:
                    response = client.get(
                        path,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    self.assertEqual(response.status_code, 200, path)

    def test_integration_accepts_the_login_cookie(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        token = jwt.encode({"username": "test-user"}, secret, algorithm="HS256")

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with TestClient(app) as client:
                client.cookies.set("access_token", token)
                response = client.get("/api/v1/gsc/health")

        self.assertEqual(response.status_code, 200)

    def test_me_returns_user_data_from_the_auth_cookie(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        token = jwt.encode(
            {
                "id": "user-id",
                "username": "test-user",
                "fullname": "Test User",
            },
            secret,
            algorithm="HS256",
        )

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with TestClient(app) as client:
                client.cookies.set("access_token", token)
                response = client.get("/api/v1/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": "user-id",
                "username": "test-user",
                "fullname": "Test User",
            },
        )

    def test_me_requires_authentication(self):
        with TestClient(app) as client:
            response = client.get("/api/v1/me")

        self.assertEqual(response.status_code, 401)

    def test_invalid_bearer_token_is_rejected_for_all_integrations(self):
        secret = "test-secret-that-is-at-least-32-bytes"

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with TestClient(app) as client:
                for path in self.integration_health_routes:
                    response = client.get(
                        path,
                        headers={"Authorization": "Bearer invalid-token"},
                    )
                    self.assertEqual(response.status_code, 401, path)

    def test_verify_token_reads_the_login_cookie(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        token = jwt.encode({"username": "test-user"}, secret, algorithm="HS256")

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with TestClient(app) as client:
                client.cookies.set("access_token", token)
                response = client.get("/api/v1/auth/verify-token")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["status"])


if __name__ == "__main__":
    unittest.main()
