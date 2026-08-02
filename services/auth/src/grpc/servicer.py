"""Auth Connect servicer implementation."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import bcrypt
import jwt
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_common import RateLimiter, RevocationStore, current_context
from llamatrade_common.auth import user_token_verification_key
from llamatrade_common.utils import verify_api_key
from llamatrade_db import get_session_maker, set_rls_bypass
from llamatrade_events.catalog.notifications import NotificationEvent, shared_notification_events
from llamatrade_proto.generated import auth_pb2, common_pb2, events_pb2
from llamatrade_telemetry import metrics

from src.client_ip import trusted_client_ip
from src.redis_client import get_redis
from src.services.tokens import (
    PURPOSE_EMAIL_VERIFY,
    PURPOSE_PASSWORD_RESET,
    consume_token,
    issue_token,
)
from src.session import (
    PasswordPolicyError,
    create_tenant_and_user,
    mint_access_refresh,
    validate_password_strength,
)

if TYPE_CHECKING:
    from llamatrade_db.models import User

logger = logging.getLogger(__name__)

# Pinned to the configured key material: RS256 public key when set, else HS256.
VERIFY_KEY, VERIFY_ALGORITHM = user_token_verification_key()

# Precomputed hash checked when the user lookup misses, so a miss and a wrong
# password take comparable time (no user-enumeration timing oracle).
_DUMMY_PASSWORD_HASH: bytes = bcrypt.hashpw(b"llamatrade-timing-pad", bcrypt.gensalt())


def _mask_key(api_key: str) -> str:
    """Masked key prefix for display; the full key and the secret are never returned."""
    return f"{api_key[:8]}…" if api_key else ""


def _user_to_proto(user: User) -> auth_pb2.User:
    """Map a DB user row to the auth User proto — the single source for every
    response that returns a user (login/register/refresh/get)."""
    return auth_pb2.User(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        roles=[user.role],
        is_active=user.is_active,
        avatar_url=user.avatar_url or "",
        created_at=common_pb2.Timestamp(seconds=int(user.created_at.timestamp())),
        last_login=common_pb2.Timestamp(seconds=int(user.last_login.timestamp()))
        if user.last_login
        else None,
    )


async def _notify_security(
    tenant_id: object,
    user_id: object,
    category: events_pb2.NotificationCategory.ValueType,
    *,
    reason: str = "",
    link: str = "",
    dedup_parts: tuple[str, ...],
) -> None:
    """Fire-and-forget security notification (welcome, password change, lockout)."""
    event = NotificationEvent(category=category, reason=reason)
    if link:
        event.extra["link"] = link
    await shared_notification_events().publish_safe(
        event,
        tenant_id=str(tenant_id),
        user_id=str(user_id),
        dedup_parts=dedup_parts,
    )


class AuthServicer:
    """Connect servicer for the Auth service.

    Implements the AuthService Protocol defined in auth_connect.py.
    Provides authentication, token validation, and user management.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        redis = get_redis()
        # Brute-force protection must not be disabled by a Redis outage, so the
        # limiter fails closed (a Redis error refuses rather than allows).
        self._rate_limiter: RateLimiter | None = (
            RateLimiter(redis, fail_closed=True) if redis is not None else None
        )
        self._revocation: RevocationStore | None = (
            RevocationStore(redis) if redis is not None else None
        )

    def _client_ip(self, ctx: AnyContext) -> str | None:
        """Client IP from a trusted ``x-forwarded-for`` position (see ``trusted_client_ip``)."""
        return trusted_client_ip(ctx.request_headers().get("x-forwarded-for", ""))

    async def _enforce_rate_limit(self, key: str, rules: tuple[tuple[int, int], ...]) -> None:
        """Apply ``(limit, window_seconds)`` rules; RESOURCE_EXHAUSTED when any trips."""
        if self._rate_limiter is None:
            return
        for limit, window in rules:
            if not await self._rate_limiter.check_and_count(key, limit, window):
                raise ConnectError(Code.RESOURCE_EXHAUSTED, "Too many attempts; try again later")

    async def _enforce_credential_rate_limits(
        self, action: str, email: str, ip: str | None, rules: tuple[tuple[int, int], ...]
    ) -> None:
        """Enforce the per-email bucket (always) and the per-IP bucket (when a
        trusted client IP is present) for a credential-taking RPC.

        The email bucket is first-class: a rotated or spoofed source IP cannot
        lift the per-target-email limit, which is the guard that actually bounds
        a credential-stuffing run against a known account.
        """
        await self._enforce_rate_limit(f"{action}:email:{email.lower()}", rules)
        if ip is not None:
            await self._enforce_rate_limit(f"{action}:ip:{ip}", rules)

    async def _get_db(self) -> AsyncSession:
        """DB session for the identity authority.

        Auth legitimately operates *pre-tenant* (login by email) and
        *cross-tenant* (S2S user/tenant lookups), so its session runs with the
        RLS system bypass; per-request tenant scoping is enforced in the app
        layer (e.g. ``get_user``/``get_tenant``).
        """
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        assert self._session_maker is not None
        session: AsyncSession = self._session_maker()
        await set_rls_bypass(session, reason="auth identity authority: pre- and cross-tenant reads")
        return session

    def _get_auth_token(self, ctx: AnyContext) -> str:
        """Extract bearer token from authorization header."""
        auth_header: str = ctx.request_headers().get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise ConnectError(
                Code.UNAUTHENTICATED,
                "Missing or invalid authorization header",
            )
        return auth_header[7:]  # Remove "Bearer " prefix

    def _authenticated_principal(self, ctx: AnyContext) -> tuple[str, str]:
        """Verified ``(tenant_id, user_id)`` for the calling user.

        Trusts the principal ``AuthMiddleware`` already verified (via
        ``current_context``), which is only ever an access-token or service
        principal. Falls back to decoding the bearer only when no middleware ran
        (unit tests calling the servicer directly), and then accepts only an
        access token so a refresh token can never authorize a user RPC.
        """
        caller = current_context()
        if caller is not None:
            if caller.is_service:
                raise ConnectError(Code.UNAUTHENTICATED, "A user token is required")
            return str(caller.tenant_id), str(caller.user_id)

        token = self._get_auth_token(ctx)
        try:
            payload = jwt.decode(token, VERIFY_KEY, algorithms=[VERIFY_ALGORITHM])
        except jwt.ExpiredSignatureError:
            metrics.auth.token_validation_failure(reason="expired")
            raise ConnectError(Code.UNAUTHENTICATED, "Token expired")
        except jwt.InvalidTokenError:
            metrics.auth.token_validation_failure(reason="invalid_sig")
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token")
        if payload.get("type", "access") != "access":
            metrics.auth.token_validation_failure(reason="wrong_type")
            raise ConnectError(Code.UNAUTHENTICATED, "An access token is required")
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("sub")
        if not tenant_id or not user_id:
            metrics.auth.token_validation_failure(reason="missing_tenant")
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token: missing user or tenant ID")
        return str(tenant_id), str(user_id)

    async def validate_token(
        self,
        request: auth_pb2.ValidateTokenRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ValidateTokenResponse:
        """Validate a JWT token and return context if valid."""
        try:
            token = request.token

            try:
                payload = jwt.decode(token, VERIFY_KEY, algorithms=[VERIFY_ALGORITHM])
            except jwt.ExpiredSignatureError:
                metrics.auth.token_validation_failure(reason="expired")
                return auth_pb2.ValidateTokenResponse(valid=False)
            except jwt.InvalidTokenError:
                metrics.auth.token_validation_failure(reason="invalid_sig")
                return auth_pb2.ValidateTokenResponse(valid=False)

            tenant_id = payload.get("tenant_id")
            user_id = payload.get("sub")
            roles = payload.get("roles", [])
            token_type = payload.get("type", "access")
            exp = payload.get("exp")

            # Only a user access token is valid here; a refresh (or any other)
            # token must never report valid, mirroring decode_token_claims.
            if token_type != "access":
                metrics.auth.token_validation_failure(reason="wrong_type")
                return auth_pb2.ValidateTokenResponse(valid=False)

            if not tenant_id or not user_id:
                metrics.auth.token_validation_failure(reason="missing_tenant")
                return auth_pb2.ValidateTokenResponse(valid=False)

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
                response.expires_at.CopyFrom(common_pb2.Timestamp(seconds=int(exp)))

            return response

        except Exception as e:
            logger.error("validate_token error: %s", e, exc_info=True)
            return auth_pb2.ValidateTokenResponse(valid=False)

    async def validate_a_p_i_key(
        self,
        request: auth_pb2.ValidateAPIKeyRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ValidateAPIKeyResponse:
        """Validate an API key and return context if valid."""
        try:
            api_key = request.api_key
            required_scopes = list(request.required_scopes) if request.required_scopes else []

            async with await self._get_db() as db:
                from sqlalchemy import select

                from llamatrade_db.models import APIKey

                key_prefix = api_key[:8] if len(api_key) >= 8 else api_key

                result = await db.execute(
                    select(APIKey).where(
                        APIKey.key_prefix == key_prefix,
                        APIKey.is_active.is_(True),
                    )
                )
                db_key = next(
                    (k for k in result.scalars().all() if verify_api_key(api_key, k.key_hash)),
                    None,
                )

                if not db_key:
                    metrics.auth.api_key_validation_failure(reason="not_found")
                    return auth_pb2.ValidateAPIKeyResponse(valid=False)

                if db_key.expires_at and db_key.expires_at < datetime.now(UTC):
                    metrics.auth.api_key_validation_failure(reason="expired")
                    return auth_pb2.ValidateAPIKeyResponse(valid=False)

                scopes_raw: list[str] | None = db_key.scopes
                granted_scopes: list[str] = list(scopes_raw) if scopes_raw else []
                if required_scopes:
                    has_all_scopes = all(scope in granted_scopes for scope in required_scopes)
                    if not has_all_scopes:
                        return auth_pb2.ValidateAPIKeyResponse(
                            valid=False,
                            granted_scopes=granted_scopes,
                        )

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
        ctx: AnyContext,
    ) -> auth_pb2.RefreshTokenResponse:
        """Refresh an access token using a refresh token."""
        refresh_token = request.refresh_token

        try:
            payload = jwt.decode(refresh_token, VERIFY_KEY, algorithms=[VERIFY_ALGORITHM])
        except jwt.ExpiredSignatureError:
            metrics.auth.token_validation_failure(reason="expired")
            raise ConnectError(Code.UNAUTHENTICATED, "Refresh token expired")
        except jwt.InvalidTokenError:
            metrics.auth.token_validation_failure(reason="invalid_sig")
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid refresh token")

        if payload.get("type") != "refresh":
            raise ConnectError(Code.INVALID_ARGUMENT, "Token is not a refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid refresh token: missing user ID")

        if self._revocation is not None and await self._revocation.is_revoked(payload):
            metrics.auth.token_validation_failure(reason="revoked")
            raise ConnectError(Code.UNAUTHENTICATED, "Refresh token has been revoked")

        # Verify user still exists and is active
        async with await self._get_db() as db:
            from uuid import UUID

            from sqlalchemy import select

            from llamatrade_db.models import User

            result = await db.execute(
                select(User).where(
                    User.id == UUID(str(user_id)),
                    User.is_active.is_(True),
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.UNAUTHENTICATED, "User not found or inactive")

            # Rotation: the presented refresh token is single-use, revoked before minting.
            jti = payload.get("jti")
            exp = payload.get("exp")
            if self._revocation is not None and jti and exp:
                await self._revocation.revoke_token(str(jti), int(exp))

            tokens = mint_access_refresh(user)
            metrics.auth.token_issued(type="access")
            metrics.auth.token_issued(type="refresh")

            return auth_pb2.RefreshTokenResponse(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                access_token_expires_at=common_pb2.Timestamp(
                    seconds=int(tokens.access_expires_at.timestamp())
                ),
                refresh_token_expires_at=common_pb2.Timestamp(
                    seconds=int(tokens.refresh_expires_at.timestamp())
                ),
            )

    async def get_user(
        self,
        request: auth_pb2.GetUserRequest,
        ctx: AnyContext,
    ) -> auth_pb2.GetUserResponse:
        """Get user by ID."""
        from uuid import UUID

        user_id = UUID(request.user_id)

        async with await self._get_db() as db:
            from sqlalchemy import select

            from llamatrade_db.models import User

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            # Cross-tenant guard: a user token may only read users in its own
            # tenant; a service token (S2S) may read any. NOT_FOUND (not
            # PERMISSION_DENIED) so cross-tenant existence isn't leaked.
            caller = current_context()
            outside_tenant = (
                caller is not None
                and not caller.is_service
                and user is not None
                and user.tenant_id != caller.tenant_id
            )
            if not user or outside_tenant:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"User not found: {request.user_id}",
                )

            return auth_pb2.GetUserResponse(user=_user_to_proto(user))

    async def get_tenant(
        self,
        request: auth_pb2.GetTenantRequest,
        ctx: AnyContext,
    ) -> auth_pb2.GetTenantResponse:
        """Get tenant by ID."""
        from uuid import UUID

        tenant_id = UUID(request.tenant_id)

        # Cross-tenant guard: a user token may only read its own tenant; a
        # service token (S2S) may read any. NOT_FOUND so existence isn't leaked.
        caller = current_context()
        if caller is not None and not caller.is_service and tenant_id != caller.tenant_id:
            raise ConnectError(Code.NOT_FOUND, f"Tenant not found: {request.tenant_id}")

        async with await self._get_db() as db:
            from sqlalchemy import select

            from llamatrade_db.models import Tenant

            result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalar_one_or_none()

            if not tenant:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Tenant not found: {request.tenant_id}",
                )

            # tenant.settings is dict[str, Any] | None, convert to string values for proto
            raw_settings = tenant.settings or {}
            settings: dict[str, str] = {k: str(v) for k, v in raw_settings.items()}

            return auth_pb2.GetTenantResponse(
                tenant=auth_pb2.Tenant(
                    id=str(tenant.id),
                    name=tenant.name,
                    plan_id="",
                    is_active=tenant.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(tenant.created_at.timestamp())),
                    settings=settings,
                )
            )

    async def register(
        self,
        request: auth_pb2.RegisterRequest,
        ctx: AnyContext,
    ) -> auth_pb2.RegisterResponse:
        """Register a new user and tenant."""
        # Signup abuse guard: the per-email bucket always applies, plus a per-IP
        # bucket when a trusted client IP is present.
        await self._enforce_credential_rate_limits(
            "register", request.email, self._client_ip(ctx), rules=((5, 60), (20, 3600))
        )

        async with await self._get_db() as db:
            try:
                user, tenant = await create_tenant_and_user(
                    db,
                    email=request.email,
                    password=request.password,
                    tenant_name=request.tenant_name,
                    first_name=request.first_name or None,
                    last_name=request.last_name or None,
                )
            except PasswordPolicyError as e:
                raise ConnectError(Code.INVALID_ARGUMENT, str(e))
            except ValueError:
                raise ConnectError(Code.ALREADY_EXISTS, "Email already registered")
            await db.commit()

            metrics.auth.registration()
            await _notify_security(
                tenant.id,
                user.id,
                events_pb2.NOTIFICATION_CATEGORY_WELCOME,
                dedup_parts=(str(user.id), "welcome"),
            )
            issued = await issue_token(
                db, tenant_id=tenant.id, user_id=user.id, purpose=PURPOSE_EMAIL_VERIFY
            )
            await db.commit()
            await _notify_security(
                tenant.id,
                user.id,
                events_pb2.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION,
                link=issued.link,
                dedup_parts=(str(user.id), "verify", issued.token[:8]),
            )

            return auth_pb2.RegisterResponse(
                user=_user_to_proto(user),
                tenant=auth_pb2.Tenant(
                    id=str(tenant.id),
                    name=tenant.name,
                    plan_id="",  # Plan is set via billing service
                    is_active=tenant.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(tenant.created_at.timestamp())),
                ),
            )

    async def _notify_lockout(self, email: str) -> None:
        """Tell the real account owner their sign-in is being rate limited.

        Deduped per hour so a stuffing run produces one email, not thousands;
        a lockout on a nonexistent email notifies nobody.
        """
        from sqlalchemy import select

        from llamatrade_db.models import User

        try:
            async with await self._get_db() as db:
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()
        except Exception:
            return
        if user is None:
            return
        hour_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
        await _notify_security(
            user.tenant_id,
            user.id,
            events_pb2.NOTIFICATION_CATEGORY_ACCOUNT_LOCKED,
            dedup_parts=(str(user.id), "lockout", hour_bucket),
        )

    async def login(
        self,
        request: auth_pb2.LoginRequest,
        ctx: AnyContext,
    ) -> auth_pb2.LoginResponse:
        """Login with email and password."""
        from sqlalchemy import select

        from llamatrade_db.models import User

        # Credential-stuffing guard: the per-email bucket always applies (so a
        # rotated source IP cannot escape it), plus a per-IP bucket when a
        # trusted client IP is present; the wider window escalates a sustained
        # burst into a lockout.
        try:
            await self._enforce_credential_rate_limits(
                "login", request.email, self._client_ip(ctx), rules=((10, 60), (30, 900))
            )
        except ConnectError as limit_error:
            if limit_error.code == Code.RESOURCE_EXHAUSTED:
                await self._notify_lockout(request.email)
            raise

        async with await self._get_db() as db:
            result = await db.execute(select(User).where(User.email == request.email))
            user = result.scalar_one_or_none()

            if not user:
                # Burn a bcrypt check so a miss is not distinguishable by timing.
                await asyncio.to_thread(
                    bcrypt.checkpw, request.password.encode(), _DUMMY_PASSWORD_HASH
                )
                metrics.auth.login_failure(reason="user_not_found")
                raise ConnectError(Code.UNAUTHENTICATED, "Invalid email or password")

            if not await asyncio.to_thread(
                bcrypt.checkpw,
                request.password.encode(),
                user.password_hash.encode(),
            ):
                metrics.auth.login_failure(reason="wrong_password")
                raise ConnectError(Code.UNAUTHENTICATED, "Invalid email or password")

            if not user.is_active:
                metrics.auth.login_failure(reason="inactive")
                raise ConnectError(Code.PERMISSION_DENIED, "User account is inactive")

            user.last_login = datetime.now(UTC)
            await db.commit()

            tokens = mint_access_refresh(user)
            metrics.auth.token_issued(type="access")
            metrics.auth.token_issued(type="refresh")

            metrics.auth.login()
            return auth_pb2.LoginResponse(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                access_token_expires_at=common_pb2.Timestamp(
                    seconds=int(tokens.access_expires_at.timestamp())
                ),
                refresh_token_expires_at=common_pb2.Timestamp(
                    seconds=int(tokens.refresh_expires_at.timestamp())
                ),
                user=_user_to_proto(user),
            )

    async def change_password(
        self,
        request: auth_pb2.ChangePasswordRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ChangePasswordResponse:
        """Change user password.

        Requires authorization token in header.
        """
        from uuid import UUID

        from sqlalchemy import select

        from llamatrade_db.models import User

        _, user_id = self._authenticated_principal(ctx)

        async with await self._get_db() as db:
            result = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.NOT_FOUND, "User not found")

            if not await asyncio.to_thread(
                bcrypt.checkpw,
                request.current_password.encode(),
                user.password_hash.encode(),
            ):
                raise ConnectError(Code.INVALID_ARGUMENT, "Current password is incorrect")

            try:
                validate_password_strength(request.new_password)
            except PasswordPolicyError as e:
                raise ConnectError(Code.INVALID_ARGUMENT, str(e))

            with metrics.auth.bcrypt_hash_duration.time():
                user.password_hash = (
                    await asyncio.to_thread(
                        bcrypt.hashpw, request.new_password.encode(), bcrypt.gensalt()
                    )
                ).decode()
            await db.commit()

            # Every session issued before the change (including this one) is dead.
            if self._revocation is not None:
                await self._revocation.revoke_all_for_user(
                    str(user.id), int(datetime.now(UTC).timestamp())
                )

            await _notify_security(
                user.tenant_id,
                user.id,
                events_pb2.NOTIFICATION_CATEGORY_PASSWORD_CHANGED,
                dedup_parts=(str(user.id), "pwchange", str(int(datetime.now(UTC).timestamp()))),
            )

            return auth_pb2.ChangePasswordResponse(
                success=True,
                message="Password changed successfully",
            )

    async def request_password_reset(
        self,
        request: auth_pb2.RequestPasswordResetRequest,
        ctx: AnyContext,
    ) -> auth_pb2.RequestPasswordResetResponse:
        """Issue a reset token; the response never reveals account existence."""
        from sqlalchemy import select

        from llamatrade_db.models import User

        await self._enforce_credential_rate_limits(
            "pwreset", request.email, self._client_ip(ctx), rules=((5, 60), (20, 3600))
        )
        async with await self._get_db() as db:
            result = await db.execute(select(User).where(User.email == request.email))
            user = result.scalar_one_or_none()
            if user is not None and user.is_active:
                issued = await issue_token(
                    db,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    purpose=PURPOSE_PASSWORD_RESET,
                )
                await db.commit()
                await _notify_security(
                    user.tenant_id,
                    user.id,
                    events_pb2.NOTIFICATION_CATEGORY_PASSWORD_RESET,
                    link=issued.link,
                    dedup_parts=(str(user.id), "reset", issued.token[:8]),
                )
        return auth_pb2.RequestPasswordResetResponse(
            success=True,
            message="If that email has an account, a reset link is on its way.",
        )

    async def reset_password(
        self,
        request: auth_pb2.ResetPasswordRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ResetPasswordResponse:
        """Redeem a reset token: set the password and kill every session."""
        from sqlalchemy import select

        from llamatrade_db.models import User

        try:
            validate_password_strength(request.new_password)
        except PasswordPolicyError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

        async with await self._get_db() as db:
            token = await consume_token(db, token=request.token, purpose=PURPOSE_PASSWORD_RESET)
            if token is None:
                raise ConnectError(Code.INVALID_ARGUMENT, "Invalid or expired reset link")
            result = await db.execute(select(User).where(User.id == token.user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                raise ConnectError(Code.INVALID_ARGUMENT, "Invalid or expired reset link")
            with metrics.auth.bcrypt_hash_duration.time():
                user.password_hash = (
                    await asyncio.to_thread(
                        bcrypt.hashpw, request.new_password.encode(), bcrypt.gensalt()
                    )
                ).decode()
            await db.commit()

            if self._revocation is not None:
                await self._revocation.revoke_all_for_user(
                    str(user.id), int(datetime.now(UTC).timestamp())
                )
            await _notify_security(
                user.tenant_id,
                user.id,
                events_pb2.NOTIFICATION_CATEGORY_PASSWORD_CHANGED,
                dedup_parts=(str(user.id), "pwreset", str(int(datetime.now(UTC).timestamp()))),
            )
        return auth_pb2.ResetPasswordResponse(
            success=True, message="Password reset; sign in with your new password."
        )

    async def verify_email(
        self,
        request: auth_pb2.VerifyEmailRequest,
        ctx: AnyContext,
    ) -> auth_pb2.VerifyEmailResponse:
        """Redeem a verification token and mark the account verified."""
        from sqlalchemy import select

        from llamatrade_db.models import User

        async with await self._get_db() as db:
            token = await consume_token(db, token=request.token, purpose=PURPOSE_EMAIL_VERIFY)
            if token is None:
                raise ConnectError(Code.INVALID_ARGUMENT, "Invalid or expired verification link")
            result = await db.execute(select(User).where(User.id == token.user_id))
            user = result.scalar_one_or_none()
            if user is None:
                raise ConnectError(Code.INVALID_ARGUMENT, "Invalid or expired verification link")
            user.is_verified = True
            await db.commit()
        return auth_pb2.VerifyEmailResponse(success=True, message="Email verified.")

    async def resend_verification(
        self,
        request: auth_pb2.ResendVerificationRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ResendVerificationResponse:
        """Re-send the verification email; uniform response, rate limited."""
        from sqlalchemy import select

        from llamatrade_db.models import User

        await self._enforce_credential_rate_limits(
            "verify", request.email, self._client_ip(ctx), rules=((5, 60), (20, 3600))
        )
        async with await self._get_db() as db:
            result = await db.execute(select(User).where(User.email == request.email))
            user = result.scalar_one_or_none()
            if user is not None and user.is_active and not user.is_verified:
                issued = await issue_token(
                    db,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    purpose=PURPOSE_EMAIL_VERIFY,
                )
                await db.commit()
                await _notify_security(
                    user.tenant_id,
                    user.id,
                    events_pb2.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION,
                    link=issued.link,
                    dedup_parts=(str(user.id), "verify", issued.token[:8]),
                )
        return auth_pb2.ResendVerificationResponse(
            success=True,
            message="If that account needs verification, an email is on its way.",
        )

    async def get_current_user(
        self,
        request: auth_pb2.GetCurrentUserRequest,
        ctx: AnyContext,
    ) -> auth_pb2.GetCurrentUserResponse:
        """Get current user from authorization token."""
        from uuid import UUID

        from sqlalchemy import select

        from llamatrade_db.models import Tenant, User

        tenant_id, user_id = self._authenticated_principal(ctx)

        async with await self._get_db() as db:
            user_result = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = user_result.scalar_one_or_none()

            if not user:
                raise ConnectError(Code.NOT_FOUND, "User not found")

            tenant_result = await db.execute(select(Tenant).where(Tenant.id == UUID(tenant_id)))
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                raise ConnectError(Code.NOT_FOUND, "Tenant not found")

            return auth_pb2.GetCurrentUserResponse(
                user=_user_to_proto(user),
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
        ctx: AnyContext,
    ) -> auth_pb2.LogoutResponse:
        """Logout: revoke the presented access token (and its refresh, if supplied)."""
        token = self._get_auth_token(ctx)

        try:
            payload = jwt.decode(token, VERIFY_KEY, algorithms=[VERIFY_ALGORITHM])
        except jwt.ExpiredSignatureError:
            # Token already expired, logout is successful
            return auth_pb2.LogoutResponse(success=True)
        except jwt.InvalidTokenError:
            metrics.auth.token_validation_failure(reason="invalid_sig")
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token")

        if self._revocation is not None:
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                await self._revocation.revoke_token(str(jti), int(exp))
            # The paired refresh token rides an extra header (LogoutRequest is empty).
            refresh = ctx.request_headers().get("x-refresh-token", "")
            if refresh:
                await self._revoke_refresh_token(refresh)

        logger.info("User logged out successfully")
        return auth_pb2.LogoutResponse(success=True)

    async def _revoke_refresh_token(self, refresh_token: str) -> None:
        """Revoke a supplied refresh token's jti; invalid tokens are ignored."""
        if self._revocation is None:
            return
        try:
            payload = jwt.decode(refresh_token, VERIFY_KEY, algorithms=[VERIFY_ALGORITHM])
        except jwt.InvalidTokenError:
            return
        if payload.get("type") != "refresh":
            return
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            await self._revocation.revoke_token(str(jti), int(exp))

    async def check_permission(
        self,
        request: auth_pb2.CheckPermissionRequest,
        ctx: AnyContext,
    ) -> auth_pb2.CheckPermissionResponse:
        """Check if user has permission for a resource/action."""
        # Authorize off the *verified* roles (the JWT), not body-supplied roles.
        # Fall back to the wire only with no middleware context (unit tests).
        caller = current_context()
        roles = list(caller.roles) if caller is not None else list(request.context.roles)
        resource = request.resource
        action = request.action

        if "admin" in roles:
            return auth_pb2.CheckPermissionResponse(
                allowed=True,
                reason="Admin role has full access",
            )

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

        for role in roles:
            if role in role_permissions:
                perms = role_permissions[role]
                # Check wildcard
                if "*" in perms and "*" in perms["*"]:
                    return auth_pb2.CheckPermissionResponse(allowed=True)
                if resource in perms:
                    if action in perms[resource] or "*" in perms[resource]:
                        return auth_pb2.CheckPermissionResponse(allowed=True)

        return auth_pb2.CheckPermissionResponse(
            allowed=False,
            reason=f"No role has permission for {action} on {resource}",
        )

    async def create_alpaca_credentials(
        self,
        request: auth_pb2.CreateAlpacaCredentialsRequest,
        ctx: AnyContext,
    ) -> auth_pb2.CreateAlpacaCredentialsResponse:
        """Create new Alpaca credentials for the authenticated tenant."""
        from uuid import UUID

        from src.models import AlpacaCredentialsCreate
        from src.services.tenant_service import TenantService

        tenant_id, _ = self._authenticated_principal(ctx)

        async with await self._get_db() as db:
            service = TenantService(db)
            creds = await service.create_alpaca_credentials(
                tenant_id=UUID(tenant_id),
                data=AlpacaCredentialsCreate(
                    name=request.name,
                    api_key=request.api_key,
                    api_secret=request.api_secret,
                    is_paper=request.is_paper,
                ),
            )

            # Write-only: never return the secret, and only a masked key prefix —
            # credentials are set once and never read back (broker-setup B1).
            return auth_pb2.CreateAlpacaCredentialsResponse(
                credentials=auth_pb2.AlpacaCredentials(
                    id=str(creds.id),
                    name=creds.name,
                    api_key=_mask_key(creds.api_key),
                    api_secret="",
                    is_paper=creds.is_paper,
                    is_active=creds.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(creds.created_at.timestamp())),
                )
            )

    async def get_alpaca_credentials(
        self,
        request: auth_pb2.GetAlpacaCredentialsRequest,
        ctx: AnyContext,
    ) -> auth_pb2.GetAlpacaCredentialsResponse:
        """Get Alpaca credentials by ID."""
        from uuid import UUID

        from src.services.tenant_service import TenantService

        tenant_id, _ = self._authenticated_principal(ctx)

        async with await self._get_db() as db:
            service = TenantService(db)
            creds = await service.get_alpaca_credentials(
                credentials_id=UUID(request.credentials_id),
                tenant_id=UUID(tenant_id),
            )

            if not creds:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Credentials not found: {request.credentials_id}",
                )

            # Write-only: never return the secret, only a masked key prefix.
            return auth_pb2.GetAlpacaCredentialsResponse(
                credentials=auth_pb2.AlpacaCredentials(
                    id=str(creds.id),
                    name=creds.name,
                    api_key=_mask_key(creds.api_key),
                    api_secret="",
                    is_paper=creds.is_paper,
                    is_active=creds.is_active,
                    created_at=common_pb2.Timestamp(seconds=int(creds.created_at.timestamp())),
                )
            )

    async def list_alpaca_credentials(
        self,
        request: auth_pb2.ListAlpacaCredentialsRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ListAlpacaCredentialsResponse:
        """List all Alpaca credentials for the authenticated tenant."""
        from uuid import UUID

        from src.services.tenant_service import TenantService

        tenant_id, _ = self._authenticated_principal(ctx)

        async with await self._get_db() as db:
            service = TenantService(db)
            creds_list = await service.list_alpaca_credentials(tenant_id=UUID(tenant_id))

            return auth_pb2.ListAlpacaCredentialsResponse(
                credentials=[
                    auth_pb2.AlpacaCredentialsListItem(
                        id=str(c.id),
                        name=c.name,
                        api_key_prefix=c.api_key_prefix,
                        is_paper=c.is_paper,
                        is_active=c.is_active,
                        created_at=common_pb2.Timestamp(seconds=int(c.created_at.timestamp())),
                    )
                    for c in creds_list
                ]
            )

    async def delete_alpaca_credentials(
        self,
        request: auth_pb2.DeleteAlpacaCredentialsRequest,
        ctx: AnyContext,
    ) -> auth_pb2.DeleteAlpacaCredentialsResponse:
        """Delete Alpaca credentials (soft delete), refusing while dependents exist."""
        from uuid import UUID

        from src.services.tenant_service import CredentialsInUseError, TenantService

        tenant_id, _ = self._authenticated_principal(ctx)

        async with await self._get_db() as db:
            service = TenantService(db)
            try:
                deleted = await service.delete_alpaca_credentials(
                    credentials_id=UUID(request.credentials_id),
                    tenant_id=UUID(tenant_id),
                )
            except CredentialsInUseError as e:
                raise ConnectError(Code.FAILED_PRECONDITION, str(e)) from e

            if not deleted:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Credentials not found: {request.credentials_id}",
                )

            return auth_pb2.DeleteAlpacaCredentialsResponse(success=True)

    async def validate_alpaca_credentials(
        self,
        request: auth_pb2.ValidateAlpacaCredentialsRequest,
        ctx: AnyContext,
    ) -> auth_pb2.ValidateAlpacaCredentialsResponse:
        """Validate Alpaca API credentials against the broker without persisting them."""
        from llamatrade_alpaca import AlpacaCredentials, TradingClient
        from llamatrade_alpaca.errors import AuthenticationError

        tenant_id, _ = self._authenticated_principal(ctx)

        # Broker probes are expensive: keyed per authenticated tenant.
        await self._enforce_rate_limit(
            f"alpaca_validate:{tenant_id or 'unknown'}",
            rules=((10, 60),),
        )

        if not request.api_key or not request.api_secret:
            return auth_pb2.ValidateAlpacaCredentialsResponse(
                valid=False, message="API key and secret are required"
            )

        creds = AlpacaCredentials(api_key=request.api_key, api_secret=request.api_secret)
        try:
            async with TradingClient(
                credentials=creds, paper=request.is_paper, timeout=10.0
            ) as client:
                account = await client.get_account()
            return auth_pb2.ValidateAlpacaCredentialsResponse(
                valid=True,
                account_status=account.status,
                buying_power=str(account.buying_power),
            )
        except AuthenticationError:
            # Rejected on the selected environment; probe the other to flag a paper/live mismatch.
            other_ok = False
            try:
                async with TradingClient(
                    credentials=creds, paper=not request.is_paper, timeout=10.0
                ) as alt:
                    await alt.get_account()
                other_ok = True
            except Exception:
                other_ok = False
            if other_ok:
                other = "live" if request.is_paper else "paper"
                return auth_pb2.ValidateAlpacaCredentialsResponse(
                    valid=False,
                    message=f"These look like {other} keys — switch the environment to {other}.",
                )
            return auth_pb2.ValidateAlpacaCredentialsResponse(
                valid=False, message="Invalid API key or secret"
            )
        except Exception as exc:
            raise ConnectError(Code.UNAVAILABLE, f"Could not reach Alpaca: {exc}")
