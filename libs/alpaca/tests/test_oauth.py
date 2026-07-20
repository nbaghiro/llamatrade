"""Alpaca OAuth helpers + bearer-credential tests."""

import httpx
import pytest
import respx

from llamatrade_alpaca import (
    AlpacaCredentials,
    OAuthToken,
    build_authorize_url,
    exchange_code,
    refresh_access_token,
)
from llamatrade_alpaca.oauth import TOKEN_URL


def test_build_authorize_url_paper() -> None:
    url = build_authorize_url(
        client_id="cid",
        redirect_uri="https://app.example/cb",
        scope="trading data",
        state="xyz",
        paper=True,
    )
    assert url.startswith("https://app.alpaca.markets/oauth/authorize?")
    assert "response_type=code" in url
    assert "client_id=cid" in url
    assert "env=paper" in url
    assert "state=xyz" in url
    assert "scope=trading+data" in url
    assert "redirect_uri=https%3A%2F%2Fapp.example%2Fcb" in url


def test_build_authorize_url_live() -> None:
    url = build_authorize_url(
        client_id="c", redirect_uri="r", scope="trading", state="s", paper=False
    )
    assert "env=live" in url


def test_credentials_bearer_headers() -> None:
    creds = AlpacaCredentials(access_token="tok123")
    assert creds.to_headers() == {"Authorization": "Bearer tok123"}
    assert creds.is_valid()


def test_credentials_key_secret_headers() -> None:
    creds = AlpacaCredentials(api_key="k", api_secret="s")
    assert creds.to_headers() == {"APCA-API-KEY-ID": "k", "APCA-API-SECRET-KEY": "s"}
    assert creds.is_valid()


def test_credentials_token_takes_precedence() -> None:
    creds = AlpacaCredentials(api_key="k", api_secret="s", access_token="tok")
    assert creds.to_headers() == {"Authorization": "Bearer tok"}


def test_credentials_invalid_when_empty() -> None:
    assert not AlpacaCredentials().is_valid()


@respx.mock
async def test_exchange_code_parses_token() -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc", "token_type": "bearer", "scope": "trading"}
        )
    )
    token = await exchange_code(
        code="code1", client_id="cid", client_secret="sec", redirect_uri="https://app/cb"
    )
    assert isinstance(token, OAuthToken)
    assert token.access_token == "abc"
    assert token.scope == "trading"
    assert token.refresh_token is None
    assert token.expires_in is None


@respx.mock
async def test_exchange_code_captures_refresh_and_expiry() -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "abc",
                "token_type": "bearer",
                "scope": "trading",
                "refresh_token": "r1",
                "expires_in": 900,
            },
        )
    )
    token = await exchange_code(
        code="c", client_id="cid", client_secret="sec", redirect_uri="https://app/cb"
    )
    assert token.refresh_token == "r1"
    assert token.expires_in == 900


@respx.mock
async def test_refresh_access_token_sends_refresh_grant() -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new", "token_type": "bearer"})
    )
    token = await refresh_access_token(refresh_token="r1", client_id="cid", client_secret="sec")
    assert token.access_token == "new"
    assert b"grant_type=refresh_token" in route.calls.last.request.content


@respx.mock
async def test_exchange_code_raises_on_missing_access_token() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"token_type": "bearer"}))
    with pytest.raises(ValueError, match="missing access_token"):
        await exchange_code(code="c", client_id="c", client_secret="s", redirect_uri="r")
