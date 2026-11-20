import unittest
import os
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException, Response
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

from app.api.v1.routers.client_routes import (
    _gen_token,
    register_client,
    update_current_user,
)
from app.requestModels.req_models import ClientUpdateRequest, RegisterRequest


class RegisterClientTests(unittest.TestCase):
    def setUp(self):
        self.users = Mock()
        self.database = MagicMock()
        self.database.__getitem__.return_value = self.users
        self.users.insert_one.return_value.inserted_id = "user-id"

    def _registration_request(self):
        return RegisterRequest(
            username="nikhilTas",
            fullname="Nikhil",
            password="example-password",
            integrations={
                "gsc": {
                    "enabled": True,
                    "property_url": "https://example.com/",
                },
                "ga4": {
                    "enabled": True,
                    "property_id": "565126740",
                },
                "google_sheets": {
                    "enabled": True,
                    "property_id": "1X0yjGxLbbb6ThX6aVT3m5Jyl5S8xikuZrhWtHRomjS0",
                },
            },
        )

    @patch("app.api.v1.routers.client_routes.get_database")
    @patch("app.api.v1.routers.client_routes._gen_token")
    def test_saves_hashed_password_and_integrations(
        self, gen_token, get_database
    ):
        get_database.return_value = self.database
        request = self._registration_request()

        response = register_client(request, Response())

        self.users.create_index.assert_called_once_with("username", unique=True)
        document = self.users.insert_one.call_args.args[0]
        self.assertNotIn("password", document)
        self.assertNotEqual(document["password_hash"], request.password)
        self.assertTrue(document["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertEqual(document["integrations"], request.integrations.model_dump())
        self.assertEqual(
            response,
            {
                "id": "user-id",
                "username": "nikhilTas",
                "fullname": "Nikhil",
                "integrations": request.integrations.model_dump(),
            },
        )
        gen_token.assert_called_once()

    @patch("app.api.v1.routers.client_routes.get_database")
    def test_returns_conflict_for_duplicate_username(self, get_database):
        get_database.return_value = self.database
        self.users.insert_one.side_effect = DuplicateKeyError("duplicate username")
        request = self._registration_request()

        with self.assertRaises(HTTPException) as error:
            register_client(request, Response())

        self.assertEqual(error.exception.status_code, 409)

    def test_auth_cookie_allows_cross_site_frontend_requests(self):
        response = Response()

        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "test-secret-that-is-at-least-32-bytes",
                "JWT_ALG": "HS256",
            },
        ):
            _gen_token({"id": "user-id"}, response)

        cookie = response.headers["set-cookie"].lower()
        self.assertIn("samesite=none", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("httponly", cookie)

    @patch("app.api.v1.routers.client_routes._gen_token")
    @patch("app.api.v1.routers.client_routes.get_database")
    def test_updates_only_the_authenticated_client_and_refreshes_name_token(
        self,
        get_database,
        gen_token,
    ):
        user_id = str(ObjectId())
        self.users.update_one.return_value.matched_count = 1
        self.users.find_one.return_value = {
            "username": "nikhilTas",
            "fullname": "New Name",
            "integrations": {
                "gsc": {
                    "enabled": True,
                    "property_url": "https://new-example.com/",
                },
                "ga4": None,
                "google_sheets": None,
            },
        }
        get_database.return_value = self.database
        gen_token.return_value = "refreshed-token"
        request = ClientUpdateRequest(
            fullname="  New Name  ",
            integrations={
                "gsc": {
                    "enabled": True,
                    "property_url": "https://new-example.com/",
                }
            },
        )
        response = Response()

        result = update_current_user(
            request,
            response,
            {"id": user_id, "username": "old-name"},
        )

        self.users.update_one.assert_called_once()
        query = self.users.update_one.call_args.args[0]
        update = self.users.update_one.call_args.args[1]
        self.assertEqual(query, {"_id": ObjectId(user_id)})
        self.assertEqual(update["$set"]["fullname"], "New Name")
        self.assertEqual(
            update["$set"]["integrations"],
            request.integrations.model_dump(),
        )
        self.assertEqual(result["fullname"], "New Name")
        self.assertNotIn("password_hash", result)
        gen_token.assert_called_once_with(
            {
                "id": user_id,
                "username": "nikhilTas",
                "fullname": "New Name",
            },
            response,
        )

    def test_client_update_requires_at_least_one_field(self):
        with self.assertRaises(ValueError):
            ClientUpdateRequest()

    def test_client_update_rejects_unrecognized_fields(self):
        with self.assertRaises(ValueError):
            ClientUpdateRequest(id="another-client", fullname="New Name")


if __name__ == "__main__":
    unittest.main()
