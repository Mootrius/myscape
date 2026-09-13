"""Pydantic request/response shapes for the API."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PlayerCreate(BaseModel):
    email: str


class PlayerOut(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None
    runescape_name: Optional[str] = None
    account_hash: Optional[str] = None

    class Config:
        from_attributes = True


class LinkStartRequest(BaseModel):
    player_id: uuid.UUID


class LinkStartResponse(BaseModel):
    code: str
    expires_at: datetime


class LinkExchangeRequest(BaseModel):
    code: str
    account_hash: str
    runescape_name: Optional[str] = None


class LinkExchangeResponse(BaseModel):
    api_key: str
    player_id: uuid.UUID
