"""Pydantic request/response shapes for the API."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


class PlayerOut(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None
    runescape_name: Optional[str] = None
    account_hash: Optional[str] = None

    class Config:
        from_attributes = True


class SignupRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) < 3:
            raise ValueError("That doesn't look like a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


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


class BankItemIn(BaseModel):
    item_id: int
    quantity: int

    @field_validator("item_id")
    @classmethod
    def check_item_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("item_id must be a positive integer.")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer.")
        return value


class BankSyncRequest(BaseModel):
    items: List[BankItemIn]


class BankSyncResponse(BaseModel):
    item_count: int


class BankItemOut(BaseModel):
    item_id: int
    quantity: int

    class Config:
        from_attributes = True


class BankOut(BaseModel):
    items: List[BankItemOut]
    updated_at: Optional[datetime] = None
