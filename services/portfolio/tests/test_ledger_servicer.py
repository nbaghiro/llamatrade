"""LedgerServicer proto-mapping tests — pure, no DB/network.

Covers the servicer's real logic (request/response proto translation) and the
degraded-projection read surfacing with the DB layers mocked. The thin
handler-over-DB orchestration is exercised by the integration suite.
"""

import contextlib
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType
from llamatrade_proto.generated import common_pb2, ledger_pb2

from src.grpc.ledger_servicer import (
    LedgerServicer,
    _account_to_proto,
    _amount,
    _dec,
    _sleeve_to_proto,
    _view_to_proto,
)
from src.ledger.projection import AccountProjection
from src.services.fund_service import SleeveView

ZERO = Decimal("0")


def _sleeve(stype: SleeveType, *, strategy_execution_id=None, allocated=ZERO) -> Sleeve:
    s = Sleeve(
        tenant_id=uuid4(),
        account_id=uuid4(),
        type=stype.value,
        status=SleeveStatus.ACTIVE.value,
        name="Test",
        strategy_execution_id=strategy_execution_id,
        allocated_capital=allocated,
    )
    s.id = uuid4()
    return s


def test_amount_parses_decimal() -> None:
    assert _amount(common_pb2.Decimal(value="100.50")) == Decimal("100.50")


def test_amount_empty_is_zero() -> None:
    assert _amount(common_pb2.Decimal(value="")) == Decimal("0")


def test_dec_builds_proto_decimal() -> None:
    assert _dec(Decimal("42.00")).value == "42.00"


def test_sleeve_to_proto_maps_fields_and_enums() -> None:
    s = _sleeve(SleeveType.STRATEGY, strategy_execution_id=uuid4(), allocated=Decimal("1000"))
    proto = _sleeve_to_proto(s, Decimal("750.25"))

    assert proto.id == str(s.id)
    assert proto.account_id == str(s.account_id)
    assert proto.type == ledger_pb2.SLEEVE_TYPE_STRATEGY
    assert proto.status == ledger_pb2.SLEEVE_STATUS_ACTIVE
    assert proto.strategy_execution_id == str(s.strategy_execution_id)
    assert proto.allocated_capital.value == "1000"
    assert proto.cash.balance.value == "750.25"  # projected cash
    assert proto.cash.reserved.value == "0"  # 0 when no projected reserved is passed


def test_sleeve_to_proto_base_sleeve_has_empty_execution_id() -> None:
    s = _sleeve(SleeveType.UNALLOCATED)
    proto = _sleeve_to_proto(s, Decimal("5000"))
    assert proto.type == ledger_pb2.SLEEVE_TYPE_UNALLOCATED
    assert proto.strategy_execution_id == ""


def test_view_to_proto_uses_view_cash() -> None:
    s = _sleeve(SleeveType.MANUAL)
    proto = _view_to_proto(SleeveView(sleeve=s, cash=Decimal("321")))
    assert proto.type == ledger_pb2.SLEEVE_TYPE_MANUAL
    assert proto.cash.balance.value == "321"


def test_account_to_proto_maps_fields() -> None:
    account = Account(tenant_id=uuid4(), credentials_id=uuid4(), base_currency="USD")
    account.id = uuid4()
    proto = _account_to_proto(account)
    assert proto.id == str(account.id)
    assert proto.tenant_id == str(account.tenant_id)
    assert proto.credentials_id == str(account.credentials_id)
    assert proto.base_currency == "USD"


def test_sleeve_to_proto_projected_reserved_and_realized() -> None:
    s = _sleeve(SleeveType.STRATEGY)
    proto = _sleeve_to_proto(s, Decimal("750"), Decimal("100"), Decimal("42.50"))
    assert proto.cash.reserved.value == "100"  # projected reservation total
    assert proto.realized_pnl.value == "42.50"


def test_sleeve_to_proto_defaults_without_projection() -> None:
    s = _sleeve(SleeveType.STRATEGY)
    proto = _sleeve_to_proto(s, Decimal("750"))
    assert proto.cash.reserved.value == "0"  # no off-ledger fallback; 0 when unset
    assert proto.realized_pnl.value == "0"


def test_close_sleeve_response_proto_round_trips() -> None:
    resp = ledger_pb2.CloseSleeveResponse(
        sleeve=_sleeve_to_proto(_sleeve(SleeveType.STRATEGY), Decimal("0")),
        already_closed=False,
        rehomed_cash=_dec(Decimal("2000")),
        rehomed_positions=[
            ledger_pb2.RehomedPosition(
                symbol="AAPL", qty=_dec(Decimal("10")), cost_basis=_dec(Decimal("3000"))
            )
        ],
    )
    assert resp.already_closed is False
    assert resp.rehomed_cash.value == "2000"
    assert resp.rehomed_positions[0].symbol == "AAPL"
    assert resp.rehomed_positions[0].qty.value == "10"
    assert resp.rehomed_positions[0].cost_basis.value == "3000"


def test_close_sleeve_handler_is_bound_on_the_asgi_app() -> None:
    """The Connect app binds svc.close_sleeve at construction, so this also
    guards the proto RPC name ↔ servicer method-name mapping."""
    from llamatrade_proto.generated.ledger_connect import LedgerServiceASGIApplication

    from src.grpc.ledger_servicer import LedgerServicer

    servicer = LedgerServicer()
    assert callable(servicer.close_sleeve)
    LedgerServiceASGIApplication(servicer)  # raises if close_sleeve isn't bound


# --------------------------------------------------------------------------- #
# Degraded-projection surfacing on reads
# --------------------------------------------------------------------------- #


@contextlib.asynccontextmanager
async def _fake_tenant_session(tenant_id, maker):
    db = MagicMock()
    db.commit = AsyncMock()
    yield db


def _projection(poison_events: int) -> AccountProjection:
    projection = AccountProjection()
    projection.poison_events = poison_events
    return projection


async def _call_get_sleeve(poison_events: int) -> list[tuple[Any, int]]:
    """Run get_sleeve with fully-mocked DB layers; return record_projection_read calls."""
    sleeve = _sleeve(SleeveType.MANUAL)
    servicer = LedgerServicer()
    servicer._session_factory = MagicMock()
    surfaced: list[tuple[Any, int]] = []

    repo = MagicMock()
    repo.get_sleeve = AsyncMock(return_value=sleeve)
    projector = MagicMock()
    projector.project_account = AsyncMock(return_value=_projection(poison_events))

    token = set_context(TenantContext(tenant_id=sleeve.tenant_id, user_id=uuid4()))
    try:
        with (
            patch("src.grpc.ledger_servicer.tenant_session", _fake_tenant_session),
            patch("src.grpc.ledger_servicer.SqlSleeveRepository", return_value=repo),
            patch("src.grpc.ledger_servicer.LedgerProjector", return_value=projector),
            patch(
                "src.grpc.ledger_servicer.record_projection_read",
                side_effect=lambda a, p: surfaced.append((a, p)),
            ),
        ):
            request = ledger_pb2.GetSleeveRequest(
                context=common_pb2.TenantContext(tenant_id=str(sleeve.tenant_id)),
                sleeve_id=str(sleeve.id),
            )
            response = await servicer.get_sleeve(request, cast(Any, None))
            assert response.sleeve.id == str(sleeve.id)  # degraded is still served
    finally:
        reset_context(token)
    return surfaced


@pytest.mark.asyncio
async def test_get_sleeve_surfaces_degraded_projection() -> None:
    surfaced = await _call_get_sleeve(poison_events=3)
    assert len(surfaced) == 1
    assert surfaced[0][1] == 3


@pytest.mark.asyncio
async def test_get_sleeve_clean_projection_reports_zero() -> None:
    surfaced = await _call_get_sleeve(poison_events=0)
    # Wiring is unconditional; the metrics helper no-ops at zero poison events.
    assert len(surfaced) == 1
    assert surfaced[0][1] == 0


@pytest.mark.asyncio
async def test_list_sleeves_surfaces_degraded_projection() -> None:
    sleeve = _sleeve(SleeveType.MANUAL)
    account_id = sleeve.account_id
    servicer = LedgerServicer()
    servicer._session_factory = MagicMock()
    surfaced: list[tuple[Any, int]] = []

    repo = MagicMock()
    repo.list_sleeves = AsyncMock(return_value=[sleeve])
    projector = MagicMock()
    projector.project_account = AsyncMock(return_value=_projection(1))

    token = set_context(TenantContext(tenant_id=sleeve.tenant_id, user_id=uuid4()))
    try:
        with (
            patch("src.grpc.ledger_servicer.tenant_session", _fake_tenant_session),
            patch("src.grpc.ledger_servicer.SqlSleeveRepository", return_value=repo),
            patch("src.grpc.ledger_servicer.LedgerProjector", return_value=projector),
            patch(
                "src.grpc.ledger_servicer.record_projection_read",
                side_effect=lambda a, p: surfaced.append((a, p)),
            ),
        ):
            request = ledger_pb2.ListSleevesRequest(
                context=common_pb2.TenantContext(tenant_id=str(sleeve.tenant_id)),
                account_id=str(account_id),
            )
            response = await servicer.list_sleeves(request, cast(Any, None))
            assert len(response.sleeves) == 1  # degraded is still served
    finally:
        reset_context(token)

    assert surfaced == [(account_id, 1)]


@pytest.mark.asyncio
async def test_close_sleeve_bad_account_id_is_invalid_argument() -> None:
    """A malformed account_id is rejected as INVALID_ARGUMENT, not a generic INTERNAL."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    servicer = LedgerServicer()
    request = ledger_pb2.CloseSleeveRequest(
        context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        account_id="not-a-uuid",
        sleeve_id=str(uuid4()),
    )
    with pytest.raises(ConnectError) as exc_info:
        await servicer.close_sleeve(request, cast(Any, None))
    assert exc_info.value.code == Code.INVALID_ARGUMENT
    assert "account_id" in exc_info.value.message


@pytest.mark.asyncio
async def test_apply_corporate_action_bad_account_id_is_invalid_argument() -> None:
    """A malformed account_id is rejected as INVALID_ARGUMENT, not a generic INTERNAL."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    servicer = LedgerServicer()
    request = ledger_pb2.ApplyCorporateActionRequest(
        context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        account_id="bad",
        symbol="AAPL",
        kind=ledger_pb2.CORPORATE_ACTION_KIND_SPLIT,
    )
    with pytest.raises(ConnectError) as exc_info:
        await servicer.apply_corporate_action(request, cast(Any, None))
    assert exc_info.value.code == Code.INVALID_ARGUMENT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("account_id", {"account_id": "bad"}),
        ("from_sleeve_id", {"from_sleeve_id": "bad"}),
        ("to_sleeve_id", {"to_sleeve_id": "bad"}),
    ],
)
async def test_transfer_capital_bad_uuid_is_invalid_argument(
    field: str, values: dict[str, str]
) -> None:
    """Each malformed transfer id is rejected as INVALID_ARGUMENT naming the field."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    args: dict[str, str] = {
        "account_id": str(uuid4()),
        "from_sleeve_id": str(uuid4()),
        "to_sleeve_id": str(uuid4()),
    }
    args.update(values)
    servicer = LedgerServicer()
    servicer._session_factory = MagicMock()
    request = ledger_pb2.TransferCapitalRequest(
        context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        amount=common_pb2.Decimal(value="100"),
        **args,
    )
    # Sleeve ids are parsed inside the transaction: fake the session and the
    # account lock so the parse (the subject) is reached without a database.
    with (
        patch("src.grpc.ledger_servicer.tenant_session", _fake_tenant_session),
        patch("src.grpc.ledger_servicer.lock_account_for_write", AsyncMock()),
        pytest.raises(ConnectError) as exc_info,
    ):
        await servicer.transfer_capital(request, cast(Any, None))
    assert exc_info.value.code == Code.INVALID_ARGUMENT
    assert field in exc_info.value.message


@pytest.mark.asyncio
async def test_get_holding_history_bad_account_id_is_invalid_argument() -> None:
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    servicer = LedgerServicer()
    request = ledger_pb2.GetHoldingHistoryRequest(
        context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        account_id="bad",
        symbol="SPY",
    )
    with pytest.raises(ConnectError) as exc_info:
        await servicer.get_holding_history(request, cast(Any, None))
    assert exc_info.value.code == Code.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_internal_error_withholds_detail_and_carries_a_reference() -> None:
    """A DB fault surfaces as INTERNAL with a correlation reference; the exception
    text (SQL, parameters) is logged, never returned to the client."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    servicer = LedgerServicer()
    servicer._session_factory = cast(
        Any, MagicMock(side_effect=RuntimeError("relation secret_table does not exist"))
    )
    request = ledger_pb2.TransferCapitalRequest(
        context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        account_id=str(uuid4()),
        from_sleeve_id=str(uuid4()),
        to_sleeve_id=str(uuid4()),
        amount=common_pb2.Decimal(value="100"),
    )
    with pytest.raises(ConnectError) as exc_info:
        await servicer.transfer_capital(request, cast(Any, None))
    assert exc_info.value.code == Code.INTERNAL
    assert "secret_table" not in exc_info.value.message
    assert "reference" in exc_info.value.message


@pytest.mark.asyncio
async def test_backfill_account_failure_degrades_to_none() -> None:
    """A broker/onboarding fault during backfill logs and returns None so the
    account is still created unseeded (reconciliation surfaces the gap)."""

    exploding_sleeves = MagicMock()
    exploding_sleeves.get_or_create_account = AsyncMock(
        side_effect=RuntimeError("broker exploded mid-onboard")
    )
    result = await LedgerServicer._backfill_account(
        cast(Any, MagicMock()), exploding_sleeves, uuid4(), uuid4()
    )
    assert result is None


async def _get_or_create(servicer: LedgerServicer, tenant_id, credentials_id) -> None:
    request = ledger_pb2.GetOrCreateAccountRequest(
        context=common_pb2.TenantContext(tenant_id=str(tenant_id)),
        credentials_id=str(credentials_id),
    )
    await servicer.get_or_create_account(request, cast(Any, None))


@pytest.mark.asyncio
async def test_failed_backfill_is_not_retried_on_every_call() -> None:
    """An unseeded account must not cost a broker call (and a pinned DB connection)
    on every dashboard load; a retry waits out the cooldown."""
    from src.grpc.ledger_servicer import _BackfillCooldown

    tenant_id, credentials_id = uuid4(), uuid4()
    account = Account(tenant_id=tenant_id, credentials_id=credentials_id, base_currency="USD")
    account.id = uuid4()
    account.alpaca_account_id = None
    repo = MagicMock()
    repo.get_account_by_credentials = AsyncMock(return_value=account)
    sleeves = MagicMock()
    sleeves.ensure_base_sleeves = AsyncMock(return_value={})
    projector = MagicMock()
    projector.project_account = AsyncMock(return_value=AccountProjection())
    backfill = AsyncMock(return_value=None)

    now = [0.0]
    servicer = LedgerServicer()
    servicer._session_factory = MagicMock()
    servicer._backfill_cooldown = _BackfillCooldown(300.0, clock=lambda: now[0])
    token = set_context(TenantContext(tenant_id=tenant_id, user_id=uuid4()))
    try:
        with (
            patch("src.grpc.ledger_servicer.tenant_session", _fake_tenant_session),
            patch("src.grpc.ledger_servicer.SqlSleeveRepository", return_value=repo),
            patch("src.grpc.ledger_servicer.SleeveService", return_value=sleeves),
            patch("src.grpc.ledger_servicer.LedgerProjector", return_value=projector),
            patch.object(LedgerServicer, "_backfill_account", backfill),
        ):
            await _get_or_create(servicer, tenant_id, credentials_id)
            await _get_or_create(servicer, tenant_id, credentials_id)
            assert backfill.await_count == 1

            now[0] = 301.0
            await _get_or_create(servicer, tenant_id, credentials_id)
            assert backfill.await_count == 2

            other_credentials = uuid4()
            await _get_or_create(servicer, tenant_id, other_credentials)
            assert backfill.await_count == 3
    finally:
        reset_context(token)


def test_backfill_cooldown_clears_on_success() -> None:
    from src.grpc.ledger_servicer import _BackfillCooldown

    now = [0.0]
    cooldown = _BackfillCooldown(60.0, clock=lambda: now[0])
    tenant_id, credentials_id = uuid4(), uuid4()

    assert cooldown.due(tenant_id, credentials_id)
    cooldown.record(tenant_id, credentials_id, succeeded=False)
    assert not cooldown.due(tenant_id, credentials_id)
    assert cooldown.due(uuid4(), credentials_id)
    cooldown.record(tenant_id, credentials_id, succeeded=True)
    assert cooldown.due(tenant_id, credentials_id)
