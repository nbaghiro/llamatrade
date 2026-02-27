"""Auth Connect servicer implementation."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import jwt
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade.v1 import auth_pb2, common_pb2

from src.services.database import get_session_maker

logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class AuthServicer:
    """Connect servicer for the Auth service.

    Implements the AuthService Protocol defined in auth_connect.py.
    Provides authentication, token validation, and user management.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: Any = None

    async def _get_db(self) -> AsyncSession:
        """Get a database session."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        session: AsyncSession = self._session_maker()
        return session

    def _get_auth_token(self, ctx: Any) -> str:
        """Extract bearer token from authorization header."""
        headers = getattr(ctx, "headers", {})
        auth_header: str = headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise ConnectError(
                Code.UNAUTHENTICATED,
                "Missing or invalid authorization header",
            )
        return auth_header[7:]  # Remove "Bearer " prefix

    async def validate_token(
        self,
        request: auth_pb2.ValidateTokenRequest,
        ctx: Any,
    ) -> auth_pb2.ValidateTokenResponse:
        """Validate a JWT token and return context if valid."""
        try:
            token = request.token

            # Decode and validate the JWT
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            except jwt.ExpiredSignatureError:
                return auth_pb2.ValidateTokenResponse(valid=False)
            except jwt.InvalidTokenError:
                return auth_pb2.ValidateTokenResponse(valid=False)

            # Extract context from payload
            tenant_id = payload.get("tenant_id")
            user_id = payload.get("sub")
            roles = payload.get("roles", [])
            token_type = payload.get("type", "access")
            exp = payload.get("exp")

            if not tenant_id or not user_id:
                return auth_pb2.ValidateTokenResponse(valid=False)

            # Build response
            response = auth_pb2.ValidateTokenResponse(
                valid=True,
                context=common_pb2.TenantContext(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    roles=roles,
                ),
                token_type=token_type,
            )

            if exp:
                response.expires_at.CopyFrom(
                    common_pb2.Timestamp(seconds=int(exp))
                )

            return response

        except Exception as e:
            logger.error("validate_token error: %s", e, exc_info=True)
            return auth_pb2.ValidateTokenResponse(valid=False)

    async def validate_a_p_i_key(
        self,
        request: auth_pb2.ValidateAPIKeyRequest,
        ctx: Any,
    ) -> auth_pb2.ValidateAPIKeyResponse:
        """Validate an API key and return context if valid."""
        try:
            api_key = request.api_key
            required_scopes = list(request.required_scopes) if request.required_scopes else []

            # Get API key from database
            async with await self._get_db() as db:
                from llamatrade_db.models import APIKey
                from sqlalchemy import select

                # Find API key by prefix (first 8 chars) and full hash
                key_prefix = api_key[:8] if len(api_key) >= 8 else api_key

                result = await db.execute(
                    select(APIKey).where(
                        APIKey.key_prefix == key_prefix,
                        APIKey.is_active == True,  # noqa: E712
                    )
                )
                db_key = result.scalar_one_or_none()

                if not db_key:
                    return auth_pb2.ValidateAPIKeyResponse(valid=False)

                # Verify full key (in production, would hash and compare)
                # For simplicity, we check if the key is active and not expired
                if db_key.expires_at and db_key.expires_at < datetime.now(UTC):
                    return auth_pb2.ValidateAPIKeyResponse(valid=False)

                # Check required scopes
                granted_scopes = db_key.scopes or []
                if required_scopes:
                    has_all_scopes = all(
                        scope in granted_scopes for scope in required_scopes
                    )
                    if not has_all_scopes:
                        return auth_pb2.ValidateAPIKeyResponse(
                            valid=False,
                            granted_scopes=granted_scopes,
                        )

                # Update last_used_at
                db_key.last_used_at = datetime.now(UTC)
                await db.commit()

                return auth_pb2.ValidateAPIKeyResponse(
                    valid=True,
                    context=common_pb2.TenantContext(
                        tenant_id=str(db_key.tenant_id),
                        user_id=str(db_key.user_id) if db_key.user_id else "",
                        roles=["api"],
                    ),
                    granted_scopes=granted_scopes,
                )

        except Exception as e:
            logger.error("validate_a_p_i_key error: %s", e, exc_info=True)
            return auth_pb2.ValidateAPIKeyResponse(valid=False)

    async def refresh_token(
        self,
        request: auth_pb2.RefreshTokenRequest,
        ctx: Any,
    ) -> auth_pb2.RefreshTokenResponse:
        """Refresh an access token using a refresh token."""
        refresh_token = request.refresh_token

        # Decode and validate the refresh token
        try:
            payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ConnectError(Code.UNAUTHENTICATED, "Refresh token expired")
        except jwt.InvalidTokenError:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid refresh token")

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise ConnectError(Code.INVALID_ARGUMENT, "Token is not a refresh token")

        user_id = payload.get("sub")

        # Verify user still exists and is active
        async with await self._get_db() as db:
            from uuid import UUID

            from llamatrade_db.models import User
            from sqlalchemy import select

            result = await db.execute(
                select(User).where(
                    User.id == UUID(user_id),
                    User.is_active == True,  # noqa: E712
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.UNAUTHENTICATED, "User not found or inactive")

            # Generate new tokens
            now = datetime.now(UTC)
            access_expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            refresh_expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

            access_payload = {
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id),
                "email": str(user.email),
                "roles": [user.role],
                "type": "access",
                "iat": now,
                "exp": access_expire,
            }
            new_access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

            refresh_payload = {
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id),
                "type": "refresh",
                "iat": now,
                "exp": refresh_expire,
            }
            new_refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

            return auth_pb2.RefreshTokenResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                access_token_expires_at=common_pb2.Timestamp(seconds=int(access_expire.timestamp())),
                refresh_token_expires_at=common_pb2.Timestamp(seconds=int(refresh_expire.timestamp())),
            )

    async def get_user(
        self,
        request: auth_pb2.GetUserRequest,
        ctx: Any,
    ) -> auth_pb2.GetUserResponse:
        """Get user by ID."""
        from uuid import UUID

        user_id = UUID(request.user_id)

        async with await self._get_db() as db:
            from llamatrade_db.models import User
            from sqlalchemy import select

            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"User not found: {request.user_id}",
                )

            return auth_pb2.GetUserResponse(
                user=auth_pb2.User(
                    id=str(user.id),
                    tenant_id=str(user.tenant_id),
                    email=user.email,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    roles=[user.role],
                    is_active=user.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(user.created_at.timestamp())),
                    last_login=common_pb2.Timestamp(
                        seconds=int(user.last_login.timestamp())
                    ) if user.last_login else None,
                )
            )

    async def get_tenant(
        self,
        request: auth_pb2.GetTenantRequest,
        ctx: Any,
    ) -> auth_pb2.GetTenantResponse:
        """Get tenant by ID."""
        from uuid import UUID

        tenant_id = UUID(request.tenant_id)

        async with await self._get_db() as db:
            from llamatrade_db.models import Tenant
            from sqlalchemy import select

            result = await db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()

            if not tenant:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Tenant not found: {request.tenant_id}",
                )

            return auth_pb2.GetTenantResponse(
                tenant=auth_pb2.Tenant(
                    id=str(tenant.id),
                    name=tenant.name,
                    plan_id="",
                    is_active=tenant.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(tenant.created_at.timestamp())),
                    settings=tenant.settings or {},
                )
            )

    async def register(
        self,
        request: auth_pb2.RegisterRequest,
        ctx: Any,
    ) -> auth_pb2.RegisterResponse:
        """Register a new user and tenant."""
        import bcrypt
        from uuid import uuid4

        from llamatrade_db.models import Tenant, User
        from sqlalchemy import select

        async with await self._get_db() as db:
            import re
            import secrets

            # Check if email already exists
            result = await db.execute(
                select(User).where(User.email == request.email)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                raise ConnectError(Code.ALREADY_EXISTS, "Email already registered")

            # Generate a unique slug from tenant name
            base_slug = re.sub(r"[^a-z0-9]+", "-", request.tenant_name.lower()).strip("-")
            slug = f"{base_slug}-{secrets.token_hex(4)}"

            # Create tenant
            tenant = Tenant(
                id=uuid4(),
                name=request.tenant_name,
                slug=slug,
                is_active=True,
            )
            db.add(tenant)
            await db.flush()

            # Hash password
            password_hash = bcrypt.hashpw(
                request.password.encode(), bcrypt.gensalt()
            ).decode()

            # Create user
            user = User(
                id=uuid4(),
                tenant_id=tenant.id,
                email=request.email,
                password_hash=password_hash,
                first_name=request.first_name or None,
                last_name=request.last_name or None,
                role="admin",  # First user is admin
                is_active=True,
            )
            db.add(user)
            await db.commit()

            return auth_pb2.RegisterResponse(
                user=auth_pb2.User(
                    id=str(user.id),
                    tenant_id=str(user.tenant_id),
                    email=user.email,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    roles=[user.role],
                    is_active=user.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(user.created_at.timestamp())),
                ),
                tenant=auth_pb2.Tenant(
                    id=str(tenant.id),
                    name=tenant.name,
                    plan_id="",  # Plan is set via billing service
                    is_active=tenant.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(tenant.created_at.timestamp())),
                ),
            )

    async def login(
        self,
        request: auth_pb2.LoginRequest,
        ctx: Any,
    ) -> auth_pb2.LoginResponse:
        """Login with email and password."""
        import bcrypt

        from llamatrade_db.models import User
        from sqlalchemy import select

        async with await self._get_db() as db:
            # Find user by email
            result = await db.execute(
                select(User).where(User.email == request.email)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.UNAUTHENTICATED, "Invalid email or password")

            # Verify password
            if not bcrypt.checkpw(
                request.password.encode(),
                user.password_hash.encode(),
            ):
                raise ConnectError(Code.UNAUTHENTICATED, "Invalid email or password")

            if not user.is_active:
                raise ConnectError(Code.PERMISSION_DENIED, "User account is inactive")

            # Update last login
            user.last_login = datetime.now(UTC)
            await db.commit()

            # Generate tokens
            now = datetime.now(UTC)
            access_expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            refresh_expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

            access_payload = {
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id),
                "email": user.email,
                "roles": [user.role],
                "type": "access",
                "iat": now,
                "exp": access_expire,
            }
            access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

            refresh_payload = {
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id),
                "type": "refresh",
                "iat": now,
                "exp": refresh_expire,
            }
            refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

            return auth_pb2.LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                access_token_expires_at=common_pb2.Timestamp(seconds=int(access_expire.timestamp())),
                refresh_token_expires_at=common_pb2.Timestamp(seconds=int(refresh_expire.timestamp())),
                user=auth_pb2.User(
                    id=str(user.id),
                    tenant_id=str(user.tenant_id),
                    email=user.email,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    roles=[user.role],
                    is_active=user.is_active,
                ),
            )

    async def change_password(
        self,
        request: auth_pb2.ChangePasswordRequest,
        ctx: Any,
    ) -> auth_pb2.ChangePasswordResponse:
        """Change user password.

        Requires authorization token in header.
        """
        import bcrypt
        from uuid import UUID

        from llamatrade_db.models import User
        from sqlalchemy import select

        # Get token and extract user_id
        token = self._get_auth_token(ctx)

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ConnectError(Code.UNAUTHENTICATED, "Token expired")
        except jwt.InvalidTokenError:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token")

        user_id = payload.get("sub")
        if not user_id:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token: missing user ID")

        async with await self._get_db() as db:
            result = await db.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.NOT_FOUND, "User not found")

            # Verify current password
            if not bcrypt.checkpw(
                request.current_password.encode(),
                user.password_hash.encode(),
            ):
                raise ConnectError(Code.INVALID_ARGUMENT, "Current password is incorrect")

            # Update password
            user.password_hash = bcrypt.hashpw(
                request.new_password.encode(), bcrypt.gensalt()
            ).decode()
            await db.commit()

            return auth_pb2.ChangePasswordResponse(
                success=True,
                message="Password changed successfully",
            )

    async def get_current_user(
        self,
        request: auth_pb2.GetCurrentUserRequest,
        ctx: Any,
    ) -> auth_pb2.GetCurrentUserResponse:
        """Get current user from authorization token."""
        from uuid import UUID

        from llamatrade_db.models import Tenant, User
        from sqlalchemy import select

        # Get token and extract user_id
        token = self._get_auth_token(ctx)

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ConnectError(Code.UNAUTHENTICATED, "Token expired")
        except jwt.InvalidTokenError:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token")

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        if not user_id or not tenant_id:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token: missing user or tenant ID")

        async with await self._get_db() as db:
            # Get user
            user_result = await db.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = user_result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.NOT_FOUND, "User not found")

            # Get tenant
            tenant_result = await db.execute(
                select(Tenant).where(Tenant.id == UUID(tenant_id))
            )
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                raise ConnectError(Code.NOT_FOUND, "Tenant not found")

            return auth_pb2.GetCurrentUserResponse(
                user=auth_pb2.User(
                    id=str(user.id),
                    tenant_id=str(user.tenant_id),
                    email=user.email,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    roles=[user.role],
                    is_active=user.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(user.created_at.timestamp())),
                    last_login=common_pb2.Timestamp(
                        seconds=int(user.last_login.timestamp())
                    ) if user.last_login else None,
                ),
                tenant=auth_pb2.Tenant(
                    id=str(tenant.id),
                    name=tenant.name,
                    plan_id="",
                    is_active=tenant.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(tenant.created_at.timestamp())),
                ),
            )

    async def logout(
        self,
        request: auth_pb2.LogoutRequest,
        ctx: Any,
    ) -> auth_pb2.LogoutResponse:
        """Logout and invalidate the current token.

        In a production system, this would add the token to a blocklist.
        """
        # Get token from header
        token = self._get_auth_token(ctx)

        # Validate token exists and is valid
        try:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            # Token already expired, logout is successful
            return auth_pb2.LogoutResponse(success=True)
        except jwt.InvalidTokenError:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token")

        # In production, add token to a blocklist (Redis) here
        # For now, we just return success since JWTs are stateless
        # TODO: Implement token blocklist in Redis

        logger.info("User logged out successfully")
        return auth_pb2.LogoutResponse(success=True)

    async def check_permission(
        self,
        request: auth_pb2.CheckPermissionRequest,
        ctx: Any,
    ) -> auth_pb2.CheckPermissionResponse:
        """Check if user has permission for a resource/action."""
        # Extract context
        roles = list(request.context.roles)
        resource = request.resource
        action = request.action

        # Simple RBAC implementation
        # Admin can do everything
        if "admin" in roles:
            return auth_pb2.CheckPermissionResponse(
                allowed=True,
                reason="Admin role has full access",
            )

        # Define permissions per role
        role_permissions: dict[str, dict[str, list[str]]] = {
            "admin": {"*": ["*"]},
            "trader": {
                "strategies": ["read", "create", "update"],
                "backtests": ["read", "create"],
                "orders": ["read", "create", "cancel"],
                "positions": ["read"],
                "portfolio": ["read"],
            },
            "viewer": {
                "strategies": ["read"],
                "backtests": ["read"],
                "orders": ["read"],
                "positions": ["read"],
                "portfolio": ["read"],
            },
            "api": {
                "strategies": ["read"],
                "backtests": ["read", "create"],
                "orders": ["read", "create", "cancel"],
                "positions": ["read"],
                "market_data": ["read"],
            },
        }

        # Check each role
        for role in roles:
            if role in role_permissions:
                perms = role_permissions[role]
                # Check wildcard
                if "*" in perms and "*" in perms["*"]:
                    return auth_pb2.CheckPermissionResponse(allowed=True)
                # Check specific resource
                if resource in perms:
                    if action in perms[resource] or "*" in perms[resource]:
                        return auth_pb2.CheckPermissionResponse(allowed=True)

        return auth_pb2.CheckPermissionResponse(
            allowed=False,
            reason=f"No role has permission for {action} on {resource}",
        )
