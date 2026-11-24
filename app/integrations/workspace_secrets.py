import logging

from bson import ObjectId

from app.core.security import decrypt_secret, TokenEncryptionError
from app.database.connection import get_database

logger = logging.getLogger(__name__)


def workspace_secret(workspace_id: str, field: str) -> str | None:
    workspace = get_database()["workspaces"].find_one(
        {"_id": ObjectId(workspace_id)}, {field: 1}
    )
    encrypted = (workspace or {}).get(field)
    if not encrypted:
        return None
    try:
        return decrypt_secret(encrypted)
    except TokenEncryptionError:
        logger.warning("Workspace credential unavailable: key decryption failed.")
        return None
