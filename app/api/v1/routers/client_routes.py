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
    ClientUpdateRequest,
    RegisterRequest,
    LoginRequest,
)
from app.database.connection import get_database
from app.models.client import Client
from app.middlewares.protect_route import protect_route
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import os

load_dotenv()
client_router = APIRouter()


def get_user_integration_property(
    user_id: str | None,
    integration_name: Literal["ga4", "gsc", "google_sheets"],
    property_key: Literal["property_id", "property_url"],
) -> str:
    if not isinstance(user_id, str) or not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token does not identify a valid client.",
        )

    client = get_database()["clients"].find_one(
        {"_id": ObjectId(user_id)},
        {"integrations": 1},
    )
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated client was not found.",
        )

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


def save_client(data: Client):
    db = get_database()
    document = data.model_dump()
    client_id = document["client_id"]
    created_at = document.pop("createdAt", None)
    document["updatedAt"] = datetime.now(timezone.utc)
    return db.clients.update_one(
        {"client_id": client_id},
        {
            "$set": document,
            "$setOnInsert": {
                "createdAt": created_at or datetime.now(timezone.utc)
            },
        },
        upsert=True,
    )


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
        return {"status": False, "message": "algorithm doesn't match"}

    newHash = hashlib.pbkdf2_hmac('sha256', normalPass.encode('utf-8'), bytes.fromhex(salt), int(iterations)).hex()

    return secrets.compare_digest(newHash, storedHash)

@client_router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_client(client: RegisterRequest, response: Response):
    client_col = get_database()["clients"]
    client_col.create_index("username", unique=True)

    client_document = {
        "username": client.username,
        "fullname": client.fullname,
        "password_hash": _hash_password(client.password),
        "integrations": client.integrations.model_dump(),
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = client_col.insert_one(client_document)
        print(result)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        ) from error
    genTokenData = {
        "id": str(result.inserted_id),
        "username": client.username,
        "fullname": client.fullname,
    }

    token = _gen_token(genTokenData, response)

    return {
        "id": str(result.inserted_id),
        "username": client.username,
        "fullname": client.fullname,
        "integrations": client.integrations.model_dump(),
    }

@client_router.post('/auth/login', status_code=status.HTTP_200_OK)
def login_client(client: LoginRequest, response: Response):
    db = get_database()
    client_col = db['clients']
    existingClient = client_col.find_one({"username": client.username})
    if not existingClient:
        return {"status": False, "message": "User not found in DB"}
    pass_check = _verify_pass(client.password, existingClient['password_hash'])
    if not pass_check:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid username or password"
        )
    if pass_check:
        genTokenData = {
            "id" : str(existingClient['_id']),
            "username": existingClient['username'],
            "fullname": existingClient['fullname']
        }
        _gen_token(genTokenData, response)
    
    return {"status": True, "message": "Client logged in successfully"}


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
    user_id = user.get("id")
    if not isinstance(user_id, str) or not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token does not identify a valid client.",
        )

    client = get_database()["clients"].find_one(
        {"_id": ObjectId(user_id)},
        {"username": 1, "fullname": 1, "integrations": 1},
    )
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated client was not found.",
        )

    username = client.get("username")
    fullname = client.get("fullname")
    if not isinstance(username, str) or not username:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored client profile is incomplete.",
        )
    if not isinstance(fullname, str) or not fullname:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored client profile is incomplete.",
        )

    return {
        "id": user_id,
        "username": username,
        "fullname": fullname,
        "integrations": client.get("integrations") or {},
    }


@client_router.patch("/me")
def update_current_user(
    client_update: ClientUpdateRequest,
    response: Response,
    user: dict[str, Any] = Depends(protect_route),
):
    user_id = user.get("id")
    if not isinstance(user_id, str) or not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token does not identify a valid client.",
        )

    updates = client_update.model_dump(exclude_unset=True)
    if "integrations" in updates:
        updates["integrations"] = client_update.integrations.model_dump()
    updates["updated_at"] = datetime.now(timezone.utc)

    client_collection = get_database()["clients"]
    result = client_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated client was not found.",
        )

    updated_client = client_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"password_hash": 0},
    )
    if not updated_client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated client was not found.",
        )

    if "fullname" in updates:
        token = _gen_token(
            {
                "id": user_id,
                "username": updated_client["username"],
                "fullname": updated_client["fullname"],
            },
            response,
        )
        if not isinstance(token, str):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Client data was updated, but the authentication session could not be refreshed.",
            )

    return {
        "id": user_id,
        "username": updated_client["username"],
        "fullname": updated_client["fullname"],
        "integrations": updated_client.get("integrations", {}),
    }
