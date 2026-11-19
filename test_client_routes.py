import unittest
import os
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException, Response
from pymongo.errors import DuplicateKeyError

from app.api.v1.routers.client_routes import _gen_token, register_client
from app.requestModels.req_models import RegisterRequest


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


if __name__ == "__main__":
    unittest.main()
