import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.api.v1.routers.client_routes import get_user_integration_property


class UserIntegrationPropertyTests(unittest.TestCase):
    @patch("app.api.v1.routers.client_routes.get_database")
    def test_reads_integration_property_for_authenticated_user(self, get_database):
        user_id = str(ObjectId())
        clients = Mock()
        clients.find_one.return_value = {
            "integrations": {
                "ga4": {"enabled": True, "property_id": "property-from-db"},
            },
        }
        get_database.return_value.__getitem__.return_value = clients

        property_id = get_user_integration_property(user_id, "ga4", "property_id")

        self.assertEqual(property_id, "property-from-db")
        clients.find_one.assert_called_once_with(
            {"_id": ObjectId(user_id)},
            {"integrations": 1},
        )

    @patch("app.api.v1.routers.client_routes.get_database")
    def test_rejects_token_without_a_valid_user_id(self, get_database):
        with self.assertRaises(HTTPException) as error:
            get_user_integration_property("not-an-object-id", "gsc", "property_url")

        self.assertEqual(error.exception.status_code, 401)
        get_database.assert_not_called()


if __name__ == "__main__":
    unittest.main()
