import json
import os
import unittest
from unittest.mock import patch

from app.integrations.ga4.client import SCOPES as GA4_SCOPES, get_ga4_client
from app.integrations.gsc.client import SCOPES as GSC_SCOPES, get_gsc_client
from app.integrations.googleSheets.client import (
    SCOPES as SHEETS_SCOPES,
    get_sheets_client,
)
from app.integrations.service_account import get_service_account_credentials


class ServiceAccountCredentialTests(unittest.TestCase):
    @patch(
        "app.integrations.service_account.service_account.Credentials."
        "from_service_account_info"
    )
    def test_loads_credentials_from_json_secret(self, from_service_account_info):
        service_account_info = {"client_email": "service@example.test"}
        from_service_account_info.return_value = "credentials"

        with patch.dict(
            os.environ,
            {"GSC_SERVICE_ACCOUNT_JSON": json.dumps(service_account_info)},
        ):
            result = get_service_account_credentials(
                "unused.json",
                "GSC_SERVICE_ACCOUNT_JSON",
                GSC_SCOPES,
            )

        self.assertEqual(result, "credentials")
        from_service_account_info.assert_called_once_with(
            service_account_info,
            scopes=GSC_SCOPES,
        )

    @patch(
        "app.integrations.service_account.service_account.Credentials."
        "from_service_account_file"
    )
    def test_preserves_credentials_file_support(self, from_service_account_file):
        from_service_account_file.return_value = "file-credentials"

        with patch.dict(os.environ, {}, clear=True):
            result = get_service_account_credentials(
                "service-account.json",
                "GSC_SERVICE_ACCOUNT_JSON",
                GSC_SCOPES,
            )

        self.assertEqual(result, "file-credentials")
        from_service_account_file.assert_called_once_with(
            "service-account.json",
            scopes=GSC_SCOPES,
        )

    def test_rejects_malformed_secret_json(self):
        with patch.dict(
            os.environ,
            {"GSC_SERVICE_ACCOUNT_JSON": "not-json"},
        ):
            with self.assertRaisesRegex(
                ValueError,
                "GSC_SERVICE_ACCOUNT_JSON must contain valid JSON",
            ):
                get_service_account_credentials(
                    None,
                    "GSC_SERVICE_ACCOUNT_JSON",
                    GSC_SCOPES,
                )

    def test_requires_a_secret_or_credentials_file(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "Set GSC_SERVICE_ACCOUNT_JSON",
            ):
                get_service_account_credentials(
                    None,
                    "GSC_SERVICE_ACCOUNT_JSON",
                    GSC_SCOPES,
                )

    @patch("app.integrations.gsc.client.build")
    @patch("app.integrations.gsc.client.get_service_account_credentials")
    def test_gsc_client_uses_gsc_secret(self, get_credentials, build):
        get_credentials.return_value = "credentials"

        get_gsc_client("credentials.json")

        get_credentials.assert_called_once_with(
            "credentials.json",
            "GSC_SERVICE_ACCOUNT_JSON",
            GSC_SCOPES,
        )
        build.assert_called_once_with(
            "searchconsole",
            "v1",
            credentials="credentials",
            cache_discovery=False,
        )

    @patch("app.integrations.ga4.client.BetaAnalyticsDataClient")
    @patch("app.integrations.ga4.client.get_service_account_credentials")
    def test_ga4_client_uses_ga4_secret(self, get_credentials, client_class):
        get_credentials.return_value = "credentials"

        get_ga4_client("credentials.json")

        get_credentials.assert_called_once_with(
            "credentials.json",
            "GA4_SERVICE_ACCOUNT_JSON",
            GA4_SCOPES,
        )
        client_class.assert_called_once_with(credentials="credentials")

    @patch("app.integrations.googleSheets.client.build")
    @patch(
        "app.integrations.googleSheets.client.get_service_account_credentials"
    )
    def test_sheets_client_uses_sheets_secret(self, get_credentials, build):
        get_credentials.return_value = "credentials"

        get_sheets_client("credentials.json")

        get_credentials.assert_called_once_with(
            "credentials.json",
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON",
            SHEETS_SCOPES,
        )
        build.assert_called_once_with(
            "sheets",
            "v4",
            credentials="credentials",
            cache_discovery=False,
        )


if __name__ == "__main__":
    unittest.main()
