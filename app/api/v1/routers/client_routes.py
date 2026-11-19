import hashlib
import secrets
from datetime import datetime, timezone
from dotenv import load_dotenv

from fastapi import APIRouter, Response, Cookie
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.requestModels.req_models import RegisterRequest, LoginRequest
from app.database.connection import get_database
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import os

load_dotenv()
client_router = APIRouter()

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
                samesite='lax',
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

@client_router.get('/auth/verify-token', status_code=status.HTTP_200_OK)
def verify_token(token: str | None = Cookie(default=None)):
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
