"""Tests for Google account connection, site discovery/import, and monthly report storage."""

import os
import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

import jwt
import mongomock
from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
os.environ.setdefault("JWT_ALG", "HS256")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "csecret")
os.environ.setdefault("GOOGLE_OAUTH_REDIRECT_URI", "http://api.test/api/v1/integrations/google/callback")
os.environ.setdefault("FRONTEND_URL", "http://app.test")

from app.main import app  # noqa: E402
from app.api.v1.routers.analytics_routes import _period_bounds, latest_reportable_month  # noqa: E402
from app.core.security import create_oauth_state, decrypt_secret, encrypt_secret, read_oauth_state  # noqa: E402
from app.integrations import discovery  # noqa: E402
from app.integrations.credentials import user_credentials_for_client  # noqa: E402
from app.integrations.google_oauth import build_authorization_url, credentials_for_connection  # noqa: E402

DB_MODULES = [
    "app.api.v1.routers.client_routes",
    "app.api.v1.routers.google_routes",
    "app.integrations.google_oauth",
    "app.integrations.discovery",
    "app.reports.storage",
    "app.jobs.monthly",
]


class FakeBucket:
    files: dict = {}

    def upload_from_stream(self, filename, data, metadata=None):
        file_id = ObjectId()
        FakeBucket.files[file_id] = data
        return file_id

    def open_download_stream(self, file_id):
        data = FakeBucket.files[file_id]
        return type("Stream", (), {"read": lambda self: data})()

    def delete(self, file_id):
        FakeBucket.files.pop(file_id, None)


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.db = mongomock.MongoClient().db
        FakeBucket.files = {}
        self.stack = ExitStack()
        for module in DB_MODULES:
            self.stack.enter_context(patch(f"{module}.get_database", return_value=self.db))
        self.stack.enter_context(patch("app.reports.storage._bucket", return_value=FakeBucket()))
        self.workspace_id = str(ObjectId())

    def tearDown(self):
        self.stack.close()

    def token(self, workspace_id=None):
        workspace_id = workspace_id or self.workspace_id
        return jwt.encode(
            {"id": workspace_id, "workspace_id": workspace_id, "username": "u", "fullname": "U"},
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )

    def add_connection(self, ga4_ids=("111",)):
        result = self.db.google_connections.insert_one(
            {
                "workspace_id": self.workspace_id,
                "google_sub": "sub-1",
                "email": "owner@example.com",
                "refresh_token_enc": encrypt_secret("refresh-token"),
                "scopes": ["https://www.googleapis.com/auth/webmasters.readonly"],
                "ga4_properties": [
                    {"property_id": pid, "display_name": f"GA {pid}", "account_name": "Acct", "stream_hosts": []}
                    for pid in ga4_ids
                ],
                "status": "active",
            }
        )
        return str(result.inserted_id)

    def add_site(self, connection_id, site_url="sc-domain:example.com"):
        return str(
            self.db.google_sites.insert_one(
                {
                    "workspace_id": self.workspace_id,
                    "connection_id": connection_id,
                    "site_url": site_url,
                    "display_name": discovery.display_name_for_site(site_url),
                    "permission_level": "siteOwner",
                    "ga4_suggestions": [{"property_id": "111", "display_name": "GA 111", "account_name": "Acct"}],
                }
            ).inserted_id
        )


class DiscoveryMatchingTests(unittest.TestCase):
    def test_site_host_handles_domain_and_url_prefix_properties(self):
        self.assertEqual(discovery.site_host("sc-domain:Example.com"), ("example.com", True))
        self.assertEqual(discovery.site_host("https://www.example.com/blog/"), ("example.com", False))

    def test_ga4_matching_by_host(self):
        self.assertTrue(discovery.ga4_matches_site("https://example.com/", ["example.com"]))
        self.assertTrue(discovery.ga4_matches_site("sc-domain:example.com", ["shop.example.com"]))
        self.assertFalse(discovery.ga4_matches_site("https://example.com/", ["shop.example.com"]))
        self.assertFalse(discovery.ga4_matches_site("sc-domain:example.com", ["notexample.com"]))
        self.assertEqual(discovery.host_from_uri("www.Example.com"), "example.com")


class SecurityTests(unittest.TestCase):
    def test_refresh_tokens_are_encrypted_and_round_trip(self):
        encrypted = encrypt_secret("1//refresh")
        self.assertNotIn("refresh", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "1//refresh")

    def test_oauth_state_round_trip_and_rejects_session_tokens(self):
        state = create_oauth_state("ws1", "/sites")
        self.assertEqual(read_oauth_state(state)["workspace_id"], "ws1")
        session_token = jwt.encode({"workspace_id": "ws1"}, os.environ["JWT_SECRET"], algorithm="HS256")
        with self.assertRaises(jwt.InvalidTokenError):
            read_oauth_state(session_token)

    def test_authorization_url_requests_offline_read_only_access(self):
        url = build_authorization_url("state123")
        self.assertIn("access_type=offline", url)
        self.assertIn("webmasters.readonly", url)
        self.assertIn("analytics.readonly", url)
        self.assertIn("state=state123", url)


class GoogleCallbackTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app, follow_redirects=False)

    def callback(self, cookie_workspace):
        state = create_oauth_state(self.workspace_id, "/sites")
        if cookie_workspace:
            self.client.cookies.set("access_token", self.token(cookie_workspace))
        return self.client.get(f"/api/v1/integrations/google/callback?code=abc&state={state}")

    def test_callback_rejects_a_different_signed_in_workspace(self):
        response = self.callback(str(ObjectId()))
        self.assertEqual(response.status_code, 303)
        self.assertIn("reason=session", response.headers["location"])
        self.assertEqual(self.db.google_connections.count_documents({}), 0)

    def test_callback_rejects_when_not_signed_in(self):
        response = self.callback(None)
        self.assertIn("reason=session", response.headers["location"])

    @patch("app.api.v1.routers.google_routes.sync_connection")
    @patch("app.api.v1.routers.google_routes.fetch_userinfo")
    @patch("app.api.v1.routers.google_routes.exchange_code")
    def test_callback_stores_encrypted_connection_and_syncs(self, exchange, userinfo, sync):
        exchange.return_value = {
            "access_token": "at",
            "refresh_token": "rt-secret",
            "scope": "openid https://www.googleapis.com/auth/webmasters.readonly",
        }
        userinfo.return_value = {"sub": "g-1", "email": "a@b.com", "name": "A"}
        response = self.callback(self.workspace_id)
        self.assertEqual(response.headers["location"], "http://app.test/sites?google=connected&email=a%40b.com")
        stored = self.db.google_connections.find_one({"google_sub": "g-1"})
        self.assertEqual(stored["workspace_id"], self.workspace_id)
        self.assertNotIn("rt-secret", str(stored))
        self.assertEqual(decrypt_secret(stored["refresh_token_enc"]), "rt-secret")
        sync.assert_called_once()

    def test_denied_consent_redirects_with_reason(self):
        state = create_oauth_state(self.workspace_id, "/sites")
        response = self.client.get(f"/api/v1/integrations/google/callback?error=access_denied&state={state}")
        self.assertIn("reason=denied", response.headers["location"])


class SiteImportTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        self.client.cookies.set("access_token", self.token())

    def test_list_sites_and_import_creates_linked_clients_without_duplicates(self):
        connection_id = self.add_connection()
        site_id = self.add_site(connection_id)

        listing = self.client.get("/api/v1/integrations/google/sites").json()
        self.assertEqual(len(listing["sites"]), 1)
        self.assertIsNone(listing["sites"][0]["client_id"])
        self.assertEqual(listing["ga4_properties"][connection_id][0]["property_id"], "111")

        body = {"sites": [{"site_id": site_id, "ga4_property_id": "111"}], "auto_monthly": True}
        first = self.client.post("/api/v1/integrations/google/sites/import", json=body)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(len(first.json()["created"]), 1)
        client = self.db.clients.find_one({})
        self.assertEqual(client["name"], "example.com")
        self.assertEqual(client["google_connection_id"], connection_id)
        self.assertTrue(client["auto_monthly"])
        self.assertEqual(client["integrations"]["gsc"]["property_url"], "sc-domain:example.com")
        self.assertEqual(client["integrations"]["ga4"]["property_id"], "111")

        second = self.client.post("/api/v1/integrations/google/sites/import", json=body).json()
        self.assertEqual(second["created"], [])
        self.assertEqual(len(second["updated"]), 1)
        self.assertEqual(self.db.clients.count_documents({}), 1)

        listing = self.client.get("/api/v1/integrations/google/sites").json()
        self.assertEqual(listing["sites"][0]["client_id"], str(client["_id"]))

    def test_import_rejects_ga4_property_not_owned_by_the_account(self):
        connection_id = self.add_connection()
        site_id = self.add_site(connection_id)
        response = self.client.post(
            "/api/v1/integrations/google/sites/import",
            json={"sites": [{"site_id": site_id, "ga4_property_id": "999"}]},
        )
        self.assertEqual(response.status_code, 422)

    def test_sites_from_other_workspaces_are_invisible(self):
        connection_id = self.add_connection()
        self.add_site(connection_id)
        self.client.cookies.set("access_token", self.token(str(ObjectId())))
        self.assertEqual(self.client.get("/api/v1/integrations/google/sites").json()["sites"], [])

    @patch("app.api.v1.routers.google_routes.revoke_token")
    def test_disconnect_removes_connection_and_its_sites(self, revoke):
        connection_id = self.add_connection()
        self.add_site(connection_id)
        response = self.client.delete(f"/api/v1/integrations/google/connections/{connection_id}")
        self.assertEqual(response.status_code, 200)
        revoke.assert_called_once_with("refresh-token")
        self.assertEqual(self.db.google_connections.count_documents({}), 0)
        self.assertEqual(self.db.google_sites.count_documents({}), 0)


class CredentialResolverTests(DatabaseTestCase):
    def test_client_without_connection_uses_service_account(self):
        self.assertIsNone(user_credentials_for_client({"workspace_id": self.workspace_id}))

    def test_disconnected_account_gives_clear_error(self):
        with self.assertRaises(HTTPException) as caught:
            user_credentials_for_client({"workspace_id": self.workspace_id, "google_connection_id": str(ObjectId())})
        self.assertEqual(caught.exception.status_code, 409)

    def test_connected_account_builds_refreshable_credentials(self):
        connection_id = self.add_connection()
        credentials = user_credentials_for_client({"workspace_id": self.workspace_id, "google_connection_id": connection_id})
        self.assertEqual(credentials.refresh_token, "refresh-token")
        self.assertEqual(credentials.client_id, os.environ["GOOGLE_OAUTH_CLIENT_ID"])
        connection = self.db.google_connections.find_one({})
        self.assertEqual(credentials_for_connection(connection).refresh_token, "refresh-token")


class MonthTests(unittest.TestCase):
    def test_explicit_month_bounds_and_previous_month(self):
        self.assertEqual(
            _period_bounds("monthly", month=date(2026, 3, 1)),
            (date(2026, 3, 1), date(2026, 3, 31), date(2026, 2, 1), date(2026, 2, 28)),
        )
        self.assertEqual(
            _period_bounds("monthly", month=date(2026, 1, 1))[2:],
            (date(2025, 12, 1), date(2025, 12, 31)),
        )

    def test_latest_reportable_month_waits_for_the_fourth(self):
        self.assertEqual(latest_reportable_month(date(2026, 11, 4)), date(2026, 10, 1))
        self.assertEqual(latest_reportable_month(date(2026, 11, 3)), date(2026, 9, 1))
        self.assertEqual(latest_reportable_month(date(2026, 1, 20)), date(2025, 12, 1))


def _dashboard(*args, **kwargs):
    return {
        "client": {"name": "Acme"},
        "period": {"start_date": "2026-10-01", "end_date": "2026-10-31"},
        "sources": {"gsc": {"status": "available"}},
    }


class ReportStorageTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client_id = str(
            self.db.clients.insert_one(
                {"workspace_id": self.workspace_id, "name": "Acme & Co", "auto_monthly": True, "integrations": {}}
            ).inserted_id
        )
        self.stack.enter_context(patch("app.api.v1.routers.analytics_routes._dashboard_from_database", side_effect=_dashboard))
        self.stack.enter_context(patch("app.reports.storage.generate_analytics_pdf", return_value=b"%PDF-1.4 fake"))
        self.refresh = self.stack.enter_context(
            patch(
                "app.api.v1.routers.analytics_routes.refresh_sources",
                return_value={"gsc": {"status": "refreshed"}, "ga4": {"status": "not_configured"}, "google_sheets": {"status": "error"}},
            )
        )

    def test_generate_stores_pdf_replaces_old_one_and_logs_run(self):
        from app.reports.storage import generate_monthly_report, read_report_file

        first = generate_monthly_report(self.workspace_id, self.client_id, date(2026, 10, 1))
        self.assertEqual(first["filename"], "Acme_Co_Monthly_202610.pdf")
        self.assertEqual(first["month"], "2026-10")
        self.assertEqual(len(first["warnings"]), 1)  # sheets failure is a warning, not a failure
        second = generate_monthly_report(self.workspace_id, self.client_id, date(2026, 10, 1))
        self.assertEqual(self.db.reports.count_documents({}), 1)
        self.assertEqual(len(FakeBucket.files), 1)
        stored = self.db.reports.find_one({})
        self.assertEqual(read_report_file(stored), b"%PDF-1.4 fake")
        self.assertEqual(second["report_id"], first["report_id"])
        self.assertEqual(self.db.report_runs.count_documents({"status": "success"}), 2)

    def test_search_console_failure_stores_nothing(self):
        from app.reports.storage import ReportGenerationError, generate_monthly_report

        self.refresh.return_value = {"gsc": {"status": "error", "detail": "Google access expired"}, "ga4": {}, "google_sheets": {}}
        with self.assertRaises(ReportGenerationError):
            generate_monthly_report(self.workspace_id, self.client_id, date(2026, 10, 1))
        self.assertEqual(self.db.reports.count_documents({}), 0)
        self.assertEqual(FakeBucket.files, {})
        run = self.db.report_runs.find_one({})
        self.assertEqual(run["status"], "failed")
        self.assertIn("Search Console", run["error"])

    def test_api_generate_list_download(self):
        client = TestClient(app)
        client.cookies.set("access_token", self.token())
        base = f"/api/v1/clients/{self.client_id}/reports"
        created = client.post(f"{base}/monthly/generate", json={"month": "2026-10"})
        self.assertEqual(created.status_code, 201, created.text)
        report_id = created.json()["report"]["report_id"]
        listing = client.get(base).json()
        self.assertEqual([r["report_id"] for r in listing["reports"]], [report_id])
        self.assertEqual(listing["runs"][0]["status"], "success")
        download = client.get(f"{base}/{report_id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.content.startswith(b"%PDF"))
        self.assertIn("Acme_Co_Monthly_202610.pdf", download.headers["content-disposition"])

        other = TestClient(app)
        other.cookies.set("access_token", self.token(str(ObjectId())))
        self.assertEqual(other.get(f"{base}/{report_id}/download").status_code, 404)

    def test_api_rejects_current_or_future_month(self):
        client = TestClient(app)
        client.cookies.set("access_token", self.token())
        response = client.post(f"/api/v1/clients/{self.client_id}/reports/monthly/generate", json={"month": "2099-01"})
        self.assertEqual(response.status_code, 422)


class MonthlyJobTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.auto = str(self.db.clients.insert_one({"workspace_id": self.workspace_id, "name": "Auto", "auto_monthly": True}).inserted_id)
        self.db.clients.insert_one({"workspace_id": self.workspace_id, "name": "Manual", "auto_monthly": False})
        self.generate = self.stack.enter_context(
            patch("app.jobs.monthly.generate_monthly_report", return_value={"report_id": "r1"})
        )

    def test_waits_until_the_fourth(self):
        from app.jobs.monthly import run_monthly_reports

        self.assertEqual(run_monthly_reports(today=date(2026, 11, 2))["status"], "skipped")
        self.generate.assert_not_called()

    def test_generates_only_auto_clients_and_skips_existing(self):
        from app.jobs.monthly import run_monthly_reports

        result = run_monthly_reports(today=date(2026, 11, 5))
        self.assertEqual(result["month"], "2026-10")
        self.assertEqual(result["summary"]["generated"], 1)
        self.generate.assert_called_once_with(self.workspace_id, self.auto, date(2026, 10, 1), refresh=True, trigger="scheduled")

        self.db.reports.insert_one({"workspace_id": self.workspace_id, "client_id": self.auto, "period": "monthly", "month": "2026-10"})
        self.generate.reset_mock()
        result = run_monthly_reports(today=date(2026, 11, 6))
        self.assertEqual(result["summary"]["existing"], 1)
        self.generate.assert_not_called()

    def test_cron_endpoint_requires_secret(self):
        client = TestClient(app)
        with patch.dict(os.environ, {"CRON_SECRET": "s3cret"}):
            self.assertEqual(client.post("/api/v1/internal/cron/monthly").status_code, 401)
            self.assertEqual(client.post("/api/v1/internal/cron/monthly", headers={"X-Cron-Secret": "nope"}).status_code, 401)
            with patch("app.api.v1.routers.cron_routes.run_monthly_reports", return_value={"status": "done"}) as job:
                response = client.post("/api/v1/internal/cron/monthly?wait=true", headers={"X-Cron-Secret": "s3cret"})
            self.assertEqual(response.json(), {"status": "done"})
            job.assert_called_once()


if __name__ == "__main__":
    unittest.main()
