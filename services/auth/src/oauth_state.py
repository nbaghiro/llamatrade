"""Signed, short-TTL state for the Alpaca OAuth redirect (CSRF protection).

The auth service has no Redis, so ``state`` is a self-verifying signed JWT (HS256
over ``JWT_SECRET``) rather than server-stored. It carries the flow ``intent`` and,
for a settings link, the initiating tenant/user, plus a random nonce. The short
TTL bounds replay; the authorization ``code`` itself is single-use at Alpaca.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

import jwt

_ALGORITHM = "HS256"
_DEFAULT_SECRET = "dev-secret-change-in-production"
_PURPOSE = "alpaca_oauth_state"
STATE_TTL_SECONDS = 600


@dataclass
class OAuthState:
    """Verified contents of an OAuth ``state`` token."""

    intent: str  # "link" | "auth"
    tenant_id: str | None = None
    user_id: str | None = None
    nonce: str = ""


def mint_state(
    intent: str,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    secret: str | None = None,
    ttl_seconds: int = STATE_TTL_SECONDS,
) -> str:
    """Mint a signed state token for the authorize redirect."""
    secret = secret or os.getenv("JWT_SECRET", _DEFAULT_SECRET)
    now = int(time.time())
    payload = {
        "purpose": _PURPOSE,
        "intent": intent,
        "nonce": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if user_id:
        payload["user_id"] = user_id
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_state(token: str, *, secret: str | None = None) -> OAuthState | None:
    """Verify a state token's signature/expiry, or return None if invalid."""
    secret = secret or os.getenv("JWT_SECRET", _DEFAULT_SECRET)
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    intent = payload.get("intent")
    if intent not in ("link", "auth"):
        return None
    tenant_id = payload.get("tenant_id")
    user_id = payload.get("user_id")
    return OAuthState(
        intent=str(intent),
        tenant_id=str(tenant_id) if tenant_id else None,
        user_id=str(user_id) if user_id else None,
        nonce=str(payload.get("nonce", "")),
    )
