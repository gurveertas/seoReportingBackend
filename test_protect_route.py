import os
import unittest
from unittest.mock import MagicMock, patch

import jwt
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import app


class ProtectRouteTests(unittest.TestCase):
    client_id = "000000000000000000000001"

    @property
    def integration_health_routes(self):
        prefix = f"/api/v1/clients/{self.client_id}"
        return (
            f"{prefix}/gsc/health",
            f"{prefix}/ga4/health",
            f"{prefix}/google-sheets/health",
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

    def test_workspace_and_client_routes_require_authentication(self):
        client_path = f"/api/v1/clients/{self.client_id}"
        requests = (
            ("GET", f"{client_path}/gsc/health", None),
            ("GET", f"{client_path}/gsc/sites", None),
            (
                "POST",
                f"{client_path}/gsc/search-performance",
                {
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-18",
                    "dimensions": ["query"],
                },
            ),
            ("GET", f"{client_path}/ga4/health", None),
            (
                "POST",
                f"{client_path}/ga4/report",
                {
                    "start_date": "7daysAgo",
                    "end_date": "yesterday",
                },
            ),
            ("GET", f"{client_path}/google-sheets/health", None),
            (
                "POST",
                f"{client_path}/google-sheets/values",
                {"range_name": "Tab!A1:B2"},
            ),
            ("GET", f"{client_path}/analytics/monthly", None),
            ("GET", f"{client_path}/analytics/weekly", None),
            ("GET", f"{client_path}/reports/monthly", None),
            ("GET", f"{client_path}/reports/weekly", None),
            ("POST", f"{client_path}/analytics/refresh", None),
            ("GET", "/api/v1/clients", None),
            ("GET", client_path, None),
            ("PATCH", client_path, {"name": "Changed Client"}),
            ("PATCH", "/api/v1/me", {"fullname": "Updated Name"}),
        )

        with TestClient(app) as client:
            for method, path, body in requests:
                response = client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401, path)

    def test_client_integration_health_routes_accept_workspace_token(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        token = jwt.encode(
            {"workspace_id": str(ObjectId())},
            secret,
            algorithm="HS256",
        )

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with patch(
                "app.api.v1.routers.gsc_routes.get_workspace_client",
                return_value={"name": "Example"},
            ), patch(
                "app.api.v1.routers.ga4_routes.get_workspace_client",
                return_value={"name": "Example"},
            ), patch(
                "app.api.v1.routers.google_sheets_routes.get_workspace_client",
                return_value={"name": "Example"},
            ):
                with TestClient(app) as client:
                    for path in self.integration_health_routes:
                        response = client.get(
                            path,
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        self.assertEqual(response.status_code, 200, path)

    def test_integration_accepts_the_login_cookie(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        token = jwt.encode(
            {"workspace_id": str(ObjectId())},
            secret,
            algorithm="HS256",
        )

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with patch(
                "app.api.v1.routers.gsc_routes.get_workspace_client",
                return_value={"name": "Example"},
            ):
                with TestClient(app) as client:
                    client.cookies.set("access_token", token)
                    response = client.get(self.integration_health_routes[0])

        self.assertEqual(response.status_code, 200)

    def test_logout_clears_auth_cookie_without_requiring_authentication(self):
        with TestClient(app) as client:
            client.cookies.set("access_token", "expired-token")
            response = client.post("/api/v1/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": True, "message": "Client logged out successfully"},
        )
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("access_token=", cookie)
        self.assertIn("max-age=0", cookie)
        self.assertIn("path=/", cookie)
        self.assertIn("samesite=none", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("httponly", cookie)

    def test_me_returns_workspace_data_from_database(self):
        secret = "test-secret-that-is-at-least-32-bytes"
        workspace_id = str(ObjectId())
        token = jwt.encode(
            {
                "id": workspace_id,
                "workspace_id": workspace_id,
                "username": "stale-username",
                "fullname": "Stale Name",
            },
            secret,
            algorithm="HS256",
        )
        database = MagicMock()
        database["workspaces"].find_one.return_value = {
            "username": "workspace-owner",
            "fullname": "Workspace Owner",
        }

        with patch.dict(
            os.environ,
            {"JWT_SECRET": secret, "JWT_ALG": "HS256"},
        ):
            with patch(
                "app.api.v1.routers.client_routes.get_database",
                return_value=database,
            ):
                with TestClient(app) as client:
                    client.cookies.set("access_token", token)
                    response = client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": workspace_id,
                "workspace_id": workspace_id,
                "username": "workspace-owner",
                "fullname": "Workspace Owner",
            },
        )
        database["workspaces"].find_one.assert_called_once_with(
            {"_id": ObjectId(workspace_id)},
            {"username": 1, "fullname": 1},
        )

    def test_me_requires_authentication(self):
        with TestClient(app) as client:
            response = client.get("/api/v1/me")

        self.assertEqual(response.status_code, 401)

    def test_invalid_bearer_token_is_rejected_for_client_integrations(self):
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
        token = jwt.encode(
            {"workspace_id": str(ObjectId())},
            secret,
            algorithm="HS256",
        )

        with patch.dict(os.environ, {"JWT_SECRET": secret, "JWT_ALG": "HS256"}):
            with TestClient(app) as client:
                client.cookies.set("access_token", token)
                response = client.get("/api/v1/auth/verify-token")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["status"])


if __name__ == "__main__":
    unittest.main()
