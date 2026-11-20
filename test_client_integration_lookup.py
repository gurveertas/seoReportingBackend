import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.api.v1.routers.client_routes import get_client_integration_property


class ClientIntegrationPropertyTests(unittest.TestCase):
    @patch("app.api.v1.routers.client_routes.get_database")
    def test_reads_property_only_from_client_owned_by_workspace(
        self,
        get_database,
    ):
        workspace_id = str(ObjectId())
        client_id = str(ObjectId())
        clients = Mock()
        clients.find_one.return_value = {
            "integrations": {
                "ga4": {"enabled": True, "property_id": "property-from-db"},
            },
        }
        get_database.return_value.__getitem__.return_value = clients

        property_id = get_client_integration_property(
            workspace_id,
            client_id,
            "ga4",
            "property_id",
        )

        self.assertEqual(property_id, "property-from-db")
        clients.find_one.assert_called_once_with(
            {
                "_id": ObjectId(client_id),
                "workspace_id": workspace_id,
            }
        )

    @patch("app.api.v1.routers.client_routes.get_database")
    def test_rejects_client_not_owned_by_workspace(self, get_database):
        workspace_id = str(ObjectId())
        client_id = str(ObjectId())
        clients = Mock()
        clients.find_one.return_value = None
        get_database.return_value.__getitem__.return_value = clients

        with self.assertRaises(HTTPException) as error:
            get_client_integration_property(
                workspace_id,
                client_id,
                "gsc",
                "property_url",
            )

        self.assertEqual(error.exception.status_code, 404)

    @patch("app.api.v1.routers.client_routes.get_database")
    def test_rejects_invalid_workspace_id_before_database_access(
        self,
        get_database,
    ):
        with self.assertRaises(HTTPException) as error:
            get_client_integration_property(
                "invalid-workspace",
                str(ObjectId()),
                "gsc",
                "property_url",
            )

        self.assertEqual(error.exception.status_code, 401)
        get_database.assert_not_called()


if __name__ == "__main__":
    unittest.main()
