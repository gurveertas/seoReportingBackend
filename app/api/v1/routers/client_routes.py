import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Literal
from dotenv import load_dotenv

from fastapi import APIRouter, Cookie, Depends, Response
from fastapi import HTTPException, status
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.requestModels.req_models import (
    ClientCreateRequest,
    ClientUpdateRequest,
    RegisterRequest,
    LoginRequest,
    WorkspaceUpdateRequest,
)
from app.database.connection import get_database
from app.models.client import Client
from app.core.security import encrypt_secret, TokenEncryptionError
from app.models.workspace import Workspace
from app.middlewares.protect_route import protect_route
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import os

load_dotenv()
client_router = APIRouter()


def get_authenticated_workspace_id(user: dict[str, Any]) -> str:
    workspace_id = user.get("workspace_id") or user.get("id")
    if not isinstance(workspace_id, str) or not ObjectId.is_valid(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token does not identify a valid workspace.",
        )
    return workspace_id


def get_workspace_client(workspace_id: str, client_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token does not identify a valid workspace.",
        )
    if not ObjectId.is_valid(client_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The client was not found in this workspace.",
        )

    client = get_database()["clients"].find_one(
        {
            "_id": ObjectId(client_id),
            "workspace_id": workspace_id,
        }
    )
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The client was not found in this workspace.",
        )
    return client


def get_client_integration_property(
    workspace_id: str,
    client_id: str,
    integration_name: Literal["ga4", "gsc", "google_sheets"],
    property_key: Literal["property_id", "property_url"],
) -> str:
    client = get_workspace_client(workspace_id, client_id)
    integration = (client.get("integrations") or {}).get(integration_name)
    if not integration or not integration.get("enabled", True):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The {integration_name} integration is not enabled for this client.",
        )

    property_value = integration.get(property_key)
    if not property_value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The {integration_name} integration has no configured {property_key}.",
        )

    return property_value


def _client_response(client: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_id": str(client["_id"]),
        "name": client["name"],
        "integrations": client.get("integrations") or {},
        "google_connection_id": client.get("google_connection_id"),
        "comparison": client.get("comparison", False),
        "auto_monthly": bool(client.get("auto_monthly", False)),
        "created_at": client.get("created_at"),
        "updated_at": client.get("updated_at"),
    }


def save_client(data: Client):
    result = get_database()["clients"].insert_one(data.model_dump())
    return result.inserted_id


def _hash_password(password: str) -> str:
    iterations = 600_000
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${password_hash.hex()}"

def _gen_token(tokenData, response):
    try:
        now = datetime.now(timezone.utc)
        payload = tokenData
        token = jwt.encode(payload, os.getenv('JWT_SECRET'), algorithm=os.getenv('JWT_ALG'))
        response.set_cookie(
                key="access_token",
                value=token,
                samesite='none',
                httponly=True,
                secure=True,
                max_age=21600,
                path='/'
            )
        return token
    except Exception as e:
        return {"status":False, "message":"Problem generating token"}

def _verify_pass(normalPass: str, hashedPass: str) -> bool:
    algorithm, iterations, salt, storedHash = hashedPass.split('$')

    if algorithm != "pbkdf2_sha256":
        return False

    newHash = hashlib.pbkdf2_hmac('sha256', normalPass.encode('utf-8'), bytes.fromhex(salt), int(iterations)).hex()

    return secrets.compare_digest(newHash, storedHash)

@client_router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_workspace(workspace: RegisterRequest, response: Response):
    workspace_collection = get_database()["workspaces"]
    workspace_collection.create_index("username", unique=True)
    workspace_document = Workspace(
        username=workspace.username,
        fullname=workspace.fullname,
        password_hash=_hash_password(workspace.password),
    ).model_dump()
    try:
        result = workspace_collection.insert_one(workspace_document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        ) from error
    workspace_id = str(result.inserted_id)
    token = _gen_token(
        {
            "id": workspace_id,
            "workspace_id": workspace_id,
            "username": workspace.username,
            "fullname": workspace.fullname,
        },
        response,
    )
    if not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workspace was created, but the authentication session could not be started.",
        )

    return {
        "id": workspace_id,
        "workspace_id": workspace_id,
        "username": workspace.username,
        "fullname": workspace.fullname,
        "clients": [],
    }

@client_router.post('/auth/login', status_code=status.HTTP_200_OK)
def login_workspace(workspace: LoginRequest, response: Response):
    db = get_database()
    workspace_collection = db["workspaces"]
    existing_workspace = workspace_collection.find_one(
        {"username": workspace.username}
    )
    if not existing_workspace:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    pass_check = _verify_pass(
        workspace.password,
        existing_workspace["password_hash"],
    )
    if not pass_check:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    workspace_id = str(existing_workspace["_id"])
    token = _gen_token(
        {
            "id": workspace_id,
            "workspace_id": workspace_id,
            "username": existing_workspace["username"],
            "fullname": existing_workspace["fullname"],
        },
        response,
    )
    if not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to start the authentication session.",
        )
    return {
        "status": True,
        "message": "Workspace logged in successfully",
        "id": workspace_id,
        "workspace_id": workspace_id,
        "username": existing_workspace["username"],
        "fullname": existing_workspace["fullname"],
    }


@client_router.post("/auth/logout", status_code=status.HTTP_200_OK)
def logout_client(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    return {"status": True, "message": "Client logged out successfully"}


@client_router.get('/auth/verify-token', status_code=status.HTTP_200_OK)
def verify_token(token: str | None = Cookie(default=None, alias="access_token")):
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token is missing from the request.",
            )
        decoded_token = jwt.decode(token, os.getenv('JWT_SECRET'), algorithms=[os.getenv('JWT_ALG')])
        return {"status": True, "message": "Token is valid", "token_data": decoded_token}
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from error


@client_router.get("/me")
@client_router.get("/auth/me", include_in_schema=False)
def get_current_user(user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    workspace = get_database()["workspaces"].find_one(
        {"_id": ObjectId(workspace_id)},
        {"username": 1, "fullname": 1, "openai_api_key_enc": 1},
    )
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated workspace was not found.",
        )

    username = workspace.get("username")
    fullname = workspace.get("fullname")
    if not isinstance(username, str) or not username:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored workspace profile is incomplete.",
        )
    if not isinstance(fullname, str) or not fullname:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored workspace profile is incomplete.",
        )

    return {
        "id": workspace_id,
        "workspace_id": workspace_id,
        "username": username,
        "fullname": fullname,
        "has_openai_api_key": bool(workspace.get("openai_api_key_enc")),
    }


@client_router.patch("/me")
def update_current_user(
    workspace_update: WorkspaceUpdateRequest,
    response: Response,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    updates = workspace_update.model_dump(exclude_unset=True)
    if "openai_api_key" in updates:
        secret = updates.pop("openai_api_key")
        key = secret.get_secret_value().strip() if secret else ""
        try:
            updates["openai_api_key_enc"] = encrypt_secret(key) if key else None
        except TokenEncryptionError as error:
            raise HTTPException(503, "Workspace secret encryption is unavailable.") from error
    updates["updated_at"] = datetime.now(timezone.utc)

    workspace_collection = get_database()["workspaces"]
    result = workspace_collection.update_one(
        {"_id": ObjectId(workspace_id)},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated workspace was not found.",
        )

    updated_workspace = workspace_collection.find_one(
        {"_id": ObjectId(workspace_id)},
        {"password_hash": 0},
    )
    if not updated_workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated workspace was not found.",
        )

    if "fullname" in updates:
        token = _gen_token(
            {
                "id": workspace_id,
                "workspace_id": workspace_id,
                "username": updated_workspace["username"],
                "fullname": updated_workspace["fullname"],
            },
            response,
        )
        if not isinstance(token, str):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Workspace data was updated, but the authentication session could not be refreshed.",
            )

    return {
        "id": workspace_id,
        "workspace_id": workspace_id,
        "username": updated_workspace["username"],
        "fullname": updated_workspace["fullname"],
        "has_openai_api_key": bool(updated_workspace.get("openai_api_key_enc")),
    }


@client_router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    client_request: ClientCreateRequest,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    collection = get_database()["clients"]
    collection.create_index("workspace_id")
    client = Client(
        workspace_id=workspace_id,
        name=client_request.name,
        integrations=client_request.integrations,
        comparison=client_request.comparison,
        auto_monthly=client_request.auto_monthly,
    )
    client_id = save_client(client)
    return _client_response(
        {
            **client.model_dump(),
            "_id": client_id,
        }
    )


@client_router.get("/clients")
def list_clients(user: dict[str, Any] = Depends(protect_route)):
    workspace_id = get_authenticated_workspace_id(user)
    clients = get_database()["clients"].find(
        {"workspace_id": workspace_id}
    ).sort("created_at", -1)
    return {"clients": [_client_response(client) for client in clients]}


@client_router.get("/clients/{client_id}")
def get_client(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    return _client_response(get_workspace_client(workspace_id, client_id))


@client_router.patch("/clients/{client_id}")
def update_client(
    client_id: str,
    client_update: ClientUpdateRequest,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    get_workspace_client(workspace_id, client_id)
    updates = client_update.model_dump(exclude_unset=True)
    if "integrations" in updates:
        if client_update.integrations is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="integrations cannot be null.",
            )
        updates["integrations"] = client_update.integrations.model_dump()
    updates["updated_at"] = datetime.now(timezone.utc)

    collection = get_database()["clients"]
    collection.update_one(
        {
            "_id": ObjectId(client_id),
            "workspace_id": workspace_id,
        },
        {"$set": updates},
    )
    updated_client = get_workspace_client(workspace_id, client_id)
    return _client_response(updated_client)


@client_router.delete("/clients/{client_id}")
def delete_client(
    client_id: str,
    user: dict[str, Any] = Depends(protect_route),
):
    workspace_id = get_authenticated_workspace_id(user)
    get_workspace_client(workspace_id, client_id)

    database = get_database()
    for collection_name in (
        "ga4_reports",
        "gsc_search_reports",
        "gsc_sites",
        "google_sheets_reports",
        "gsc_data",
    ):
        database[collection_name].delete_many(
            {
                "workspace_id": workspace_id,
                "client_id": client_id,
            }
        )

    from app.reports.storage import delete_client_reports

    delete_client_reports(workspace_id, client_id)

    result = database["clients"].delete_one(
        {
            "_id": ObjectId(client_id),
            "workspace_id": workspace_id,
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The client was not found in this workspace.",
        )

    return {
        "status": True,
        "message": "Client and its stored integration data deleted successfully.",
        "client_id": client_id,
    }
