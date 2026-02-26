"""User service - user CRUD operations."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import bcrypt
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import UserResponse, UserUpdate, UserWithPassword
from src.services.database import get_db


class UserService:
    """Service for user management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(
        self,
        tenant_id: UUID,
        email: str,
        password: str,
        role: str = "user",
    ) -> UserResponse:
        """Create a new user."""
        user_id = uuid4()
        password_hash = self._hash_password(password)
        now = datetime.now(UTC)

        query = text("""
            INSERT INTO users (
                id, tenant_id, email, password_hash, role,
                is_active, is_verified
            )
            VALUES (
                :id, :tenant_id, :email, :password_hash, :role,
                :is_active, :is_verified
            )
            RETURNING id, tenant_id, email, role, is_active, created_at
        """)

        await self.db.execute(
            query,
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": email,
                "password_hash": password_hash,
                "role": role,
                "is_active": True,
                "is_verified": False,
            },
        )

        return UserResponse(
            id=user_id,
            tenant_id=tenant_id,
            email=email,  # Pydantic v2: EmailStr is a type annotation, not callable
            role=role,
            is_active=True,
            created_at=now,
        )

    async def get_user(
        self,
        user_id: UUID,
        tenant_id: UUID | None = None,
    ) -> UserResponse | None:
        """Get a user by ID."""
        query = text("""
            SELECT id, tenant_id, email, role, is_active, created_at
            FROM users
            WHERE id = :user_id
        """)

        result = await self.db.execute(query, {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return None

        return UserResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            email=row.email,
            role=row.role,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def get_user_with_password(
        self,
        user_id: UUID,
    ) -> UserWithPassword | None:
        """Get a user by ID including password hash (for authentication)."""
        query = text("""
            SELECT id, tenant_id, email, password_hash, role, is_active, created_at
            FROM users
            WHERE id = :user_id
        """)

        result = await self.db.execute(query, {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return None

        return UserWithPassword(
            id=row.id,
            tenant_id=row.tenant_id,
            email=row.email,
            password_hash=row.password_hash,
            role=row.role,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def get_user_by_email(self, email: str) -> UserWithPassword | None:
        """Get a user by email (includes password hash for authentication)."""
        query = text("""
            SELECT id, tenant_id, email, password_hash, role, is_active, created_at
            FROM users
            WHERE email = :email
        """)

        result = await self.db.execute(query, {"email": email})
        row = result.fetchone()

        if not row:
            return None

        return UserWithPassword(
            id=row.id,
            tenant_id=row.tenant_id,
            email=row.email,
            password_hash=row.password_hash,
            role=row.role,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def list_users(
        self,
        tenant_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserResponse], int]:
        """List users in a tenant."""
        # Simplified - in production use SQLAlchemy ORM
        return [], 0

    async def update_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
        update: UserUpdate,
    ) -> UserResponse | None:
        """Update a user."""
        # Simplified - in production use SQLAlchemy ORM
        return None

    async def update_password(self, user_id: UUID, password_hash: str) -> None:
        """Update user password hash."""
        query = text("""
            UPDATE users
            SET password_hash = :password_hash
            WHERE id = :user_id
        """)
        await self.db.execute(
            query,
            {"user_id": user_id, "password_hash": password_hash},
        )

    async def delete_user(self, user_id: UUID, tenant_id: UUID) -> bool:
        """Delete a user."""
        # Simplified - in production use SQLAlchemy ORM
        return False

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed: bytes = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()


async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    """Dependency to get user service."""
    return UserService(db)
