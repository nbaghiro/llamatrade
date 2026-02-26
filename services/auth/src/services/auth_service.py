"""Authentication service - login, registration, token management."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import TokenResponse, UserResponse, UserWithPassword
from src.services.database import get_db
from src.services.tenant_service import TenantService, get_tenant_service
from src.services.user_service import UserService, get_user_service

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class AuthService:
    """Authentication service for login, registration, and token management."""

    def __init__(
        self,
        db: AsyncSession,
        user_service: UserService,
        tenant_service: TenantService,
    ):
        self.db = db
        self.user_service = user_service
        self.tenant_service = tenant_service

    async def register(
        self,
        tenant_name: str,
        email: str,
        password: str,
    ) -> UserResponse:
        """Register a new user and tenant."""
        # Check if email already exists
        existing_user = await self.user_service.get_user_by_email(email)
        if existing_user:
            raise ValueError("Email already registered")

        # Create tenant
        tenant = await self.tenant_service.create_tenant(name=tenant_name)

        # Create user with admin role
        user = await self.user_service.create_user(
            tenant_id=tenant.id,
            email=email,
            password=password,
            role="admin",
        )

        return user

    async def login(self, email: str, password: str) -> TokenResponse | None:
        """Authenticate user and return tokens."""
        user = await self.user_service.get_user_by_email(email)
        if not user:
            return None

        if not user.is_active:
            return None

        if not self._verify_password(password, user.password_hash):
            return None

        # Generate tokens
        access_token = self._create_access_token(user)
        refresh_token = self._create_refresh_token(user)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse | None:
        """Refresh access token using refresh token."""
        try:
            payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

            if payload.get("type") != "refresh":
                return None

            user_id = UUID(payload["sub"])
            user = await self.user_service.get_user(user_id=user_id)

            if not user or not user.is_active:
                return None

            # Generate new tokens
            access_token = self._create_access_token(user)
            new_refresh_token = self._create_refresh_token(user)

            return TokenResponse(
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_type="bearer",
                expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            )
        except jwt.InvalidTokenError:
            return None

    async def logout(self, user_id: UUID) -> None:
        """Logout user (invalidate tokens if using token blacklist)."""
        # For now, we don't maintain a token blacklist
        # In production, you might want to:
        # 1. Add the token to a Redis blacklist
        # 2. Or use short-lived tokens with refresh token rotation
        pass

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change user password."""
        user = await self.user_service.get_user_with_password(user_id=user_id)
        if not user:
            return False

        if not self._verify_password(current_password, user.password_hash):
            return False

        new_hash = self._hash_password(new_password)
        await self.user_service.update_password(user_id=user_id, password_hash=new_hash)
        return True

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed: bytes = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        result: bool = bcrypt.checkpw(password.encode(), password_hash.encode())
        return result

    def _create_access_token(self, user: UserResponse | UserWithPassword) -> str:
        """Create a JWT access token."""
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "email": str(user.email),
            "roles": [user.role],  # Convert single role to array for RBAC compatibility
            "type": "access",
            "iat": now,
            "exp": expire,
        }

        token: str = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token

    def _create_refresh_token(self, user: UserResponse | UserWithPassword) -> str:
        """Create a JWT refresh token."""
        now = datetime.now(UTC)
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        payload = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "type": "refresh",
            "iat": now,
            "exp": expire,
        }

        token: str = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> AuthService:
    """Dependency to get auth service."""
    return AuthService(db, user_service, tenant_service)
