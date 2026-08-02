"""Alpaca OAuth 2.0 browser-redirect routes.

OAuth is redirect-based, so this is a plain FastAPI router (mounted alongside the
Connect app, like billing's Stripe webhooks) rather than a Connect RPC.

Link flow (settings "Connect Alpaca"):
  1. POST /oauth/alpaca/start  (authenticated) → returns the authorize URL; the
     browser then navigates to it.
  2. GET  /oauth/alpaca/callback (public; Alpaca redirects here) → exchanges the
     code for a token, reads the account id, persists an OAuth credential + an
     identity link for the tenant carried in the signed ``state``, then redirects
     back to the web app.

Login/signup-with-Alpaca (``intent="auth"``) is not wired yet; see
``.docs/planning/alpaca-oauth-implementation-plan.md``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import delete, select

from llamatrade_alpaca import AlpacaCredentials as AlpacaAuth
from llamatrade_alpaca import (
    OAuthToken,
    TradingClient,
    build_authorize_url,
    exchange_code,
)
from llamatrade_common import RateLimiter, consume_once, current_context
from llamatrade_common.utils import async_encrypt_value
from llamatrade_db import get_session_maker, set_rls_bypass
from llamatrade_db.models.auth import (
    AlpacaCredentials,
    OAuthIdentity,
    OAuthPendingSignup,
    User,
)

from src.client_ip import trusted_client_ip
from src.oauth_state import mint_state, verify_state
from src.redis_client import get_redis
from src.session import (
    HANDOFF_TTL_SECONDS,
    PasswordPolicyError,
    create_tenant_and_user,
    mint_access_refresh,
    mint_handoff,
    user_to_dict,
    verify_handoff,
)

router = APIRouter()

_PROVIDER = "alpaca"


def _client_ip(request: Request) -> str | None:
    """Client IP from a trusted ``x-forwarded-for`` position (see ``trusted_client_ip``)."""
    return trusted_client_ip(request.headers.get("x-forwarded-for", ""))


async def _enforce_oauth_rate_limit(
    request: Request, name: str, rules: tuple[tuple[int, int], ...]
) -> None:
    """Fail-closed brute-force guard for the public OAuth routes, keyed per client IP.

    A no-op without Redis (unit tests, minimal deploys); a Redis outage refuses
    rather than allows so token/ticket guessing stays throttled.
    """
    redis = get_redis()
    if redis is None:
        return
    limiter = RateLimiter(redis, fail_closed=True)
    key = f"{name}:{_client_ip(request) or 'unknown'}"
    for limit, window in rules:
        if not await limiter.check_and_count(key, limit, window):
            raise HTTPException(status_code=429, detail="Too many attempts; try again later")


def _web_app_url() -> str:
    return os.getenv("WEB_APP_URL", "http://localhost:8800")


def _oauth_config() -> tuple[str, str, str, str]:
    """(client_id, client_secret, redirect_uri, scope) from env."""
    return (
        os.getenv("ALPACA_OAUTH_CLIENT_ID", ""),
        os.getenv("ALPACA_OAUTH_CLIENT_SECRET", ""),
        os.getenv("ALPACA_OAUTH_REDIRECT_URI", ""),
        os.getenv("ALPACA_OAUTH_SCOPE", "trading"),
    )


@router.post("/oauth/alpaca/start")
async def alpaca_oauth_start() -> dict[str, str]:
    """Mint the Alpaca authorize URL for the authenticated user to connect."""
    ctx = current_context()
    if ctx is None or ctx.is_service:
        raise HTTPException(status_code=401, detail="authentication required")

    client_id, _, redirect_uri, scope = _oauth_config()
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=503, detail="Alpaca OAuth is not configured")

    state = mint_state("link", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))
    url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        paper=True,
    )
    return {"authorizeUrl": url}


@router.get("/oauth/alpaca/authorize")
async def alpaca_oauth_authorize(intent: str = "auth") -> RedirectResponse:
    """Public entry for sign in / sign up with Alpaca (no session yet)."""
    if intent != "auth":
        raise HTTPException(status_code=400, detail="unsupported intent")
    client_id, _, redirect_uri, scope = _oauth_config()
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=503, detail="Alpaca OAuth is not configured")
    state = mint_state("auth")
    url = build_authorize_url(
        client_id=client_id, redirect_uri=redirect_uri, scope=scope, state=state, paper=True
    )
    return RedirectResponse(url, status_code=302)


@router.get("/oauth/alpaca/callback")
async def alpaca_oauth_callback(
    code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    """Handle Alpaca's redirect: exchange the code, then link or authenticate."""
    web = _web_app_url()
    if error:
        return RedirectResponse(f"{web}/settings?tab=broker&error={error}", status_code=302)

    verified = verify_state(state)
    if verified is None:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    if not code:
        raise HTTPException(status_code=400, detail="missing authorization code")

    client_id, client_secret, redirect_uri, _ = _oauth_config()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Alpaca OAuth is not configured")

    token = await exchange_code(
        code=code, client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
    )
    account_id = await _fetch_account_id(token.access_token)

    if verified.intent == "link":
        if not verified.tenant_id or not verified.user_id:
            raise HTTPException(status_code=400, detail="link state missing identity")
        await _persist_link(
            tenant_id=UUID(verified.tenant_id),
            user_id=UUID(verified.user_id),
            token=token,
            account_id=account_id,
        )
        return RedirectResponse(f"{web}/settings?tab=broker&connected=1", status_code=302)

    # intent == "auth": log in if the account is already linked, else stage a signup.
    return await _handle_auth_callback(web=web, token=token, account_id=account_id)


async def _fetch_account_id(access_token: str) -> str:
    """Read the Alpaca account id the token authorizes (paper env)."""
    client = TradingClient(credentials=AlpacaAuth(access_token=access_token), paper=True)
    try:
        account = await client.get_account()
        return account.id
    finally:
        await client.close()


def _token_expiry(expires_in: int | None) -> datetime | None:
    if not expires_in:
        return None
    return datetime.now(UTC) + timedelta(seconds=expires_in)


async def _persist_link(
    *, tenant_id: UUID, user_id: UUID, token: OAuthToken, account_id: str
) -> None:
    """Store the OAuth trading credential + the login identity for this account."""
    db = get_session_maker()()
    # auth is the identity authority (pre-/cross-tenant)
    await set_rls_bypass(db, reason="auth oauth link: store credential and identity")
    try:
        db.add(
            AlpacaCredentials(
                tenant_id=tenant_id,
                name="Alpaca (OAuth)",
                auth_type="oauth",
                access_token_encrypted=await async_encrypt_value(token.access_token),
                refresh_token_encrypted=(
                    await async_encrypt_value(token.refresh_token) if token.refresh_token else None
                ),
                token_expires_at=_token_expiry(token.expires_in),
                alpaca_account_id=account_id,
                is_paper=True,
                is_active=True,
            )
        )
        existing = await db.scalar(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == _PROVIDER,
                OAuthIdentity.provider_account_id == account_id,
            )
        )
        if existing is None:
            db.add(
                OAuthIdentity(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    provider=_PROVIDER,
                    provider_account_id=account_id,
                )
            )
        elif existing.user_id != user_id:
            raise HTTPException(
                status_code=409, detail="This Alpaca account is already linked to another user"
            )
        await db.commit()
    finally:
        await db.close()


async def _handle_auth_callback(
    *, web: str, token: OAuthToken, account_id: str
) -> RedirectResponse:
    """Log the user in if the Alpaca account is linked, else stage a signup."""
    db = get_session_maker()()
    await set_rls_bypass(db, reason="auth oauth callback: resolve identity or stage signup")
    try:
        identity = await db.scalar(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == _PROVIDER,
                OAuthIdentity.provider_account_id == account_id,
            )
        )
        if identity is not None:
            handoff = mint_handoff(str(identity.user_id))
            return RedirectResponse(
                f"{web}/oauth/alpaca/callback?handoff={handoff}", status_code=302
            )

        pending = OAuthPendingSignup(
            provider=_PROVIDER,
            provider_account_id=account_id,
            access_token_encrypted=await async_encrypt_value(token.access_token),
            refresh_token_encrypted=(
                await async_encrypt_value(token.refresh_token) if token.refresh_token else None
            ),
            token_expires_at=_token_expiry(token.expires_in),
            is_paper=True,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        db.add(pending)
        await db.commit()
        return RedirectResponse(f"{web}/signup/complete?ticket={pending.id}", status_code=302)
    finally:
        await db.close()


def _session_payload(user: User) -> dict[str, object]:
    ar = mint_access_refresh(user)
    return {
        "accessToken": ar.access_token,
        "refreshToken": ar.refresh_token,
        "user": user_to_dict(user),
    }


class ExchangeRequest(BaseModel):
    handoff: str


@router.post("/oauth/alpaca/exchange")
async def alpaca_oauth_exchange(body: ExchangeRequest, request: Request) -> dict[str, object]:
    """Exchange a one-time login handoff for a session (tokens + user)."""
    await _enforce_oauth_rate_limit(request, "oauth_exchange", ((10, 60), (30, 900)))
    handoff = verify_handoff(body.handoff)
    if handoff is None or not handoff.jti:
        raise HTTPException(status_code=400, detail="invalid or expired handoff")
    # Single-use: a Redis outage fails open (the 120s TTL still bounds replay).
    redis = get_redis()
    if redis is not None and not await consume_once(
        redis, f"llamatrade:auth:oauth:handoff:{handoff.jti}", HANDOFF_TTL_SECONDS
    ):
        raise HTTPException(status_code=401, detail="handoff already used")
    db = get_session_maker()()
    await set_rls_bypass(db, reason="auth oauth exchange: redeem login handoff")
    try:
        user = await db.scalar(select(User).where(User.id == UUID(handoff.user_id)))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="account not available")
        user.last_login = datetime.now(UTC)
        await db.commit()
        return _session_payload(user)
    finally:
        await db.close()


class CompleteSignupRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    ticket: str
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""


@router.post("/oauth/alpaca/complete-signup")
async def alpaca_oauth_complete_signup(
    body: CompleteSignupRequest, request: Request
) -> dict[str, object]:
    """Finish sign-up-with-Alpaca: create the account and store the connection."""
    await _enforce_oauth_rate_limit(request, "oauth_signup", ((5, 60), (20, 3600)))
    try:
        ticket_id = UUID(body.ticket)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid signup ticket") from None

    db = get_session_maker()()
    await set_rls_bypass(db, reason="auth oauth signup: create tenant and user from ticket")
    try:
        # Single-use, race-safe: atomically claim the ticket row; a concurrent
        # (or replayed) request finds nothing and gets 410. Rolls back with the
        # transaction, so a failed signup does not burn the ticket.
        result = await db.execute(
            delete(OAuthPendingSignup)
            .where(OAuthPendingSignup.id == ticket_id)
            .returning(OAuthPendingSignup)
            .execution_options(synchronize_session=False)
        )
        pending = result.scalar_one_or_none()
        if pending is None:
            raise HTTPException(status_code=410, detail="invalid or already used signup ticket")
        if pending.expires_at < datetime.now(UTC):
            raise HTTPException(status_code=410, detail="signup ticket expired")

        try:
            user, _ = await create_tenant_and_user(
                db,
                email=body.email,
                password=body.password,
                tenant_name=body.email.split("@")[0] or "My Workspace",
                first_name=body.first_name or None,
                last_name=body.last_name or None,
            )
        except PasswordPolicyError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except ValueError:
            raise HTTPException(status_code=409, detail="Email already registered") from None

        db.add(
            AlpacaCredentials(
                tenant_id=user.tenant_id,
                name="Alpaca (OAuth)",
                auth_type="oauth",
                access_token_encrypted=pending.access_token_encrypted,
                refresh_token_encrypted=pending.refresh_token_encrypted,
                token_expires_at=pending.token_expires_at,
                alpaca_account_id=pending.provider_account_id,
                is_paper=pending.is_paper,
                is_active=True,
            )
        )
        db.add(
            OAuthIdentity(
                tenant_id=user.tenant_id,
                user_id=user.id,
                provider=_PROVIDER,
                provider_account_id=pending.provider_account_id,
            )
        )
        await db.commit()
        return _session_payload(user)
    finally:
        await db.close()
