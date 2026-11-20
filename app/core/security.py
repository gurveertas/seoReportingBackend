"""Encryption for stored Google refresh tokens and signed OAuth state values."""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

_STATE_AUDIENCE = "google-oauth-state"


class TokenEncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise TokenEncryptionError(
            "TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as error:
        raise TokenEncryptionError("TOKEN_ENCRYPTION_KEY is not a valid Fernet key.") from error


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise TokenEncryptionError(
            "A stored token could not be decrypted. Was TOKEN_ENCRYPTION_KEY changed?"
        ) from error


def _jwt_settings() -> tuple[str, str]:
    secret = os.getenv("JWT_SECRET")
    algorithm = os.getenv("JWT_ALG", "HS256")
    if not secret:
        raise RuntimeError("JWT_SECRET is not set.")
    return secret, algorithm


def create_oauth_state(workspace_id: str, return_to: str | None = None) -> str:
    secret, algorithm = _jwt_settings()
    payload: dict[str, Any] = {
        "aud": _STATE_AUDIENCE,
        "workspace_id": workspace_id,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    if return_to:
        payload["return_to"] = return_to
    return jwt.encode(payload, secret, algorithm=algorithm)


def read_oauth_state(state: str) -> dict[str, Any]:
    secret, algorithm = _jwt_settings()
    return jwt.decode(state, secret, algorithms=[algorithm], audience=_STATE_AUDIENCE)
