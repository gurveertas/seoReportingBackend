
from datetime import datetime, timezone

from app.database.connection import get_database
from app.models.client import Client


def save_client(data: Client):

    db = get_database()
    document = data.model_dump()
    client_id = document["client_id"]
    createdAt = document.pop("createdAt", None)
    document["updatedAt"] = datetime.now(timezone.utc)
    result = db.clients.update_one(
        {
            "client_id": client_id
        },
        {
            "$set": document,
            "$setOnInsert": {
                "createdAt": createdAt or datetime.now(timezone.utc)
            }
        },
        upsert=True
    )
    return result
