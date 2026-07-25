"""Auth Service - Pydantic schemas for Alpaca credentials."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AlpacaCredentialsCreate(BaseModel):
    """Create a new set of Alpaca credentials."""

    name: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=20)
    api_secret: str = Field(..., min_length=40)
    is_paper: bool = True


class AlpacaCredentialsResponse(BaseModel):
    """Response with decrypted Alpaca credentials."""

    id: UUID
    name: str
    api_key: str
    api_secret: str
    is_paper: bool
    is_active: bool = True
    created_at: datetime


class AlpacaCredentialsListItem(BaseModel):
    """List item for credentials (key masked for security)."""

    id: UUID
    name: str
    api_key_prefix: str  # First 8 characters only
    is_paper: bool
    is_active: bool
    created_at: datetime
