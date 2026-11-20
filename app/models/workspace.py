from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class Workspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    fullname: str = Field(min_length=1, max_length=120)
    password_hash: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
