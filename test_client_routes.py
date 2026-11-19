import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.api.v1.routers.client_routes import register_client
from app.requestModels.req_models import RegisterRequest


class RegisterClientTests(unittest.TestCase):
    def setUp(self):
        self.users = Mock()
        self.database = MagicMock()
        self.database.__getitem__.return_value = self.users
        self.users.insert_one.return_value.inserted_id = "user-id"

    @patch("app.api.v1.routers.client_routes.get_database")
    def test_saves_hashed_password_and_returns_public_fields(self, get_database):
        get_database.return_value = self.database
        request = RegisterRequest(
            username="nikhil",
            fullname="Nikhil Ads",
            password="example-password",
        )

        response = register_client(request)

        self.users.create_index.assert_called_once_with("username", unique=True)
        document = self.users.insert_one.call_args.args[0]
        self.assertNotIn("password", document)
        self.assertNotEqual(document["password_hash"], request.password)
        self.assertTrue(document["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertEqual(
            response,
            {
                "id": "user-id",
                "username": "nikhil",
                "fullname": "Nikhil Ads",
            },
        )

    @patch("app.api.v1.routers.client_routes.get_database")
    def test_returns_conflict_for_duplicate_username(self, get_database):
        get_database.return_value = self.database
        self.users.insert_one.side_effect = DuplicateKeyError("duplicate username")
        request = RegisterRequest(
            username="nikhil",
            fullname="Nikhil Ads",
            password="example-password",
        )

        with self.assertRaises(HTTPException) as error:
            register_client(request)

        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
