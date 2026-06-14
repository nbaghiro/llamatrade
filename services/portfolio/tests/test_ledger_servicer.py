"""LedgerServicer proto-mapping tests — pure, no DB/network.

Covers the servicer's real logic (request/response proto translation). The thin
handler-over-DB orchestration is exercised by the integration suite.
"""

from decimal import Decimal
from uuid import uuid4

from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType
from llamatrade_proto.generated import common_pb2, ledger_pb2

from src.grpc.ledger_servicer import (
    _account_to_proto,
    _amount,
    _dec,
    _sleeve_to_proto,
    _view_to_proto,
)
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
        cash_balance=ZERO,
        reserved_cash=Decimal("12.50"),
        unsettled_cash=ZERO,
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
    assert proto.cash.balance.value == "750.25"  # projected cash, not the row column
    assert proto.cash.reserved.value == "12.50"


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
    assert proto.cash.reserved.value == "100"  # projection wins over the row column
    assert proto.realized_pnl.value == "42.50"


def test_sleeve_to_proto_defaults_without_projection() -> None:
    s = _sleeve(SleeveType.STRATEGY)
    proto = _sleeve_to_proto(s, Decimal("750"))
    assert proto.cash.reserved.value == "12.50"  # row column fallback
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
