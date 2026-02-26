"""Auth Service - Database models and Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# Request/Response Schemas
class TenantCreate(BaseModel):
    """Schema for creating a tenant."""

    name: str = Field(..., min_length=1, max_length=255)
    plan_id: str = Field(default="free", max_length=50)


class TenantResponse(BaseModel):
    """Schema for tenant response."""

    id: UUID
    name: str
    plan_id: str
    settings: dict[str, str | int | bool | None]
    created_at: datetime


class TenantDetailResponse(TenantResponse):
    """Schema for tenant response with slug."""

    slug: str


class UserCreate(BaseModel):
    """Schema for creating a user."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="user")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserResponse(BaseModel):
    """Schema for user response."""

    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


class UserWithPassword(BaseModel):
    """Internal model including password hash for authentication."""

    id: UUID
    tenant_id: UUID
    email: EmailStr
    password_hash: str
    role: str
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema for token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class RegisterRequest(BaseModel):
    """Schema for user registration (creates tenant and user)."""

    tenant_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class PasswordChangeRequest(BaseModel):
    """Schema for password change request."""

    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class AlpacaCredentials(BaseModel):
    """Schema for Alpaca credentials."""

    paper_key: str | None = None
    paper_secret: str | None = None
    live_key: str | None = None
    live_secret: str | None = None


class AlpacaCredentialsUpdate(BaseModel):
    """Schema for updating Alpaca credentials."""

    paper_key: str | None = None
    paper_secret: str | None = None
    live_key: str | None = None
    live_secret: str | None = None


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["read"])


class APIKeyResponse(BaseModel):
    """Schema for API key response."""

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None


class APIKeyCreatedResponse(BaseModel):
    """Schema for newly created API key (includes full key, shown only once)."""

    id: UUID
    name: str
    api_key: str  # Full key, shown only on creation
    scopes: list[str]
    created_at: datetime


class APIKeyValidationResult(BaseModel):
    """Result of API key validation."""

    user_id: UUID
    tenant_id: UUID
    email: EmailStr
    scopes: list[str]
