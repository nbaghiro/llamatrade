"""Alpaca OAuth 2.0 helpers (authorization-code flow).

Keeps the OAuth handshake — building the authorize URL and exchanging the
authorization code (or a refresh token) for a bearer access token — inside the
shared Alpaca lib, so no service talks to Alpaca's OAuth endpoints directly.
See ``.docs/planning/alpaca-oauth-implementation-plan.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode

import httpx

# Same endpoints for paper and live; the account environment is selected via the
# ``env`` query param on the authorize URL.
AUTHORIZE_URL = "https://app.alpaca.markets/oauth/authorize"
TOKEN_URL = "https://api.alpaca.markets/oauth/token"


@dataclass
class OAuthToken:
    """Token returned by Alpaca's OAuth token endpoint."""

    access_token: str
    token_type: str = "bearer"
    scope: str = ""
    refresh_token: str | None = None
    expires_in: int | None = None


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    paper: bool = True,
) -> str:
    """Build the Alpaca authorization URL to redirect the user to.

    Args:
        client_id: Registered OAuth app client id.
        redirect_uri: Whitelisted callback URI (must match the registered value).
        scope: Space-delimited scopes (e.g. ``"trading data"``).
        state: Opaque anti-CSRF value echoed back on the callback.
        paper: Restrict authorization to the paper environment.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "env": "paper" if paper else "live",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 30.0,
) -> OAuthToken:
    """Exchange an authorization code for a bearer access token (server-side)."""
    return await _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=timeout,
    )


async def refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    timeout: float = 30.0,
) -> OAuthToken:
    """Exchange a refresh token for a new access token."""
    return await _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=timeout,
    )


async def _post_token(data: dict[str, str], *, timeout: float) -> OAuthToken:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        return _parse_token(resp.json())


def _parse_token(raw: object) -> OAuthToken:
    if not isinstance(raw, dict):
        raise ValueError("Unexpected Alpaca OAuth token response")
    payload = cast(dict[str, object], raw)

    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        raise ValueError("Alpaca OAuth token response missing access_token")

    token_type = payload.get("token_type")
    scope = payload.get("scope")
    refresh = payload.get("refresh_token")
    expires = payload.get("expires_in")
    return OAuthToken(
        access_token=access,
        token_type=token_type if isinstance(token_type, str) else "bearer",
        scope=scope if isinstance(scope, str) else "",
        refresh_token=refresh if isinstance(refresh, str) and refresh else None,
        expires_in=expires if isinstance(expires, int) else None,
    )
