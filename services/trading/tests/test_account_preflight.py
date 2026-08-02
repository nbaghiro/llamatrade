"""Account preflight: cash accounts are refused; margin accounts pass."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from llamatrade_alpaca.models.trading import Account
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_LIVE, EXECUTION_MODE_PAPER

from src.credentials import DecryptedCredentials
from src.services.live_session_service import LiveSessionService


def _account(multiplier: str, buying_power: str = "10000") -> Account:
    return Account(
        id="acct-1",
        account_number="A1",
        status="ACTIVE",
        cash=Decimal("10000"),
        portfolio_value=Decimal("10000"),
        buying_power=Decimal(buying_power),
        equity=Decimal("10000"),
        multiplier=multiplier,
    )


def _creds() -> DecryptedCredentials:
    return DecryptedCredentials(
        id=uuid4(), name="paper", api_key="k", api_secret="s", is_paper=True
    )


def _service() -> LiveSessionService:
    return LiveSessionService.__new__(LiveSessionService)


async def _run_check(account: Account, mode: int) -> None:
    client = AsyncMock()
    client.get_account = AsyncMock(return_value=account)
    client.close = AsyncMock()
    with patch("src.services.live_session_service.build_trading_client", return_value=client):
        await LiveSessionService._check_alpaca_account(_service(), _creds(), mode)


@pytest.mark.asyncio
async def test_cash_account_is_refused() -> None:
    with pytest.raises(ValueError, match="margin account"):
        await _run_check(_account(multiplier="1"), EXECUTION_MODE_PAPER)


@pytest.mark.asyncio
async def test_margin_account_passes() -> None:
    await _run_check(_account(multiplier="2"), EXECUTION_MODE_PAPER)


@pytest.mark.asyncio
async def test_live_requires_buying_power_after_margin_check() -> None:
    with pytest.raises(ValueError, match="buying power"):
        await _run_check(_account(multiplier="4", buying_power="100"), EXECUTION_MODE_LIVE)
