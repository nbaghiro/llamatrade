"""Proto <-> DB enum parity guardrail.

CLAUDE.md makes the proto enums the single source of truth. The DB layer keeps a
parallel StrEnum per proto enum (``_enum_types``) plus the ledger StrEnums
(stored as VARCHAR). These are hand-maintained, so this test fails CI the moment
a DB enum drifts from its proto counterpart — the exact regression that let
``alert_condition_type`` silently drop ``RECONCILIATION_DRIFT``/``SLEEVE_FROZEN``.
"""

from typing import cast

import pytest
from google.protobuf.internal.enum_type_wrapper import EnumTypeWrapper
from sqlalchemy import Dialect

import llamatrade_db.models._enum_types as et
import llamatrade_db.models.ledger as ledger
from llamatrade_proto.generated import (
    agent_pb2,
    backtest_pb2,
    billing_pb2,
    common_pb2,
    ledger_pb2,
    notification_pb2,
    strategy_pb2,
    trading_pb2,
)

# Each proto-backed TypeDecorator paired with its canonical proto enum.
PROTO_ENUM_CASES: list[tuple[type[et._ProtoEnumType[int]], EnumTypeWrapper]] = [
    (et.OrderSideType, trading_pb2.OrderSide),
    (et.OrderTypeType, trading_pb2.OrderType),
    (et.OrderStatusType, trading_pb2.OrderStatus),
    (et.TimeInForceType, trading_pb2.TimeInForce),
    (et.PositionSideType, trading_pb2.PositionSide),
    (et.ExecutionModeType, common_pb2.ExecutionMode),
    (et.ExecutionStatusType, common_pb2.ExecutionStatus),
    (et.StrategyStatusType, strategy_pb2.StrategyStatus),
    (et.BacktestStatusType, backtest_pb2.BacktestStatus),
    (et.SubscriptionStatusType, billing_pb2.SubscriptionStatus),
    (et.PlanTierType, billing_pb2.PlanTier),
    (et.BillingIntervalType, billing_pb2.BillingInterval),
    (et.InvoiceStatusType, billing_pb2.InvoiceStatus),
    (et.NotificationTypeType, notification_pb2.NotificationType),
    (et.ChannelTypeType, notification_pb2.ChannelType),
    (et.AlertConditionTypeType, notification_pb2.AlertConditionType),
    (et.AlertStatusType, notification_pb2.AlertStatus),
    (et.NotificationStatusType, notification_pb2.NotificationStatus),
    (et.AgentSessionStatusType, agent_pb2.AgentSessionStatus),
    (et.MessageRoleType, agent_pb2.MessageRole),
    (et.ArtifactTypeType, agent_pb2.ArtifactType),
]


def _proto_nonzero_values(proto_enum: EnumTypeWrapper) -> set[int]:
    """Proto enum values excluding the ``*_UNSPECIFIED`` zero sentinel."""
    return {v for v in proto_enum.values() if not proto_enum.Name(v).endswith("_UNSPECIFIED")}


@pytest.mark.parametrize(
    "type_decorator,proto_enum", PROTO_ENUM_CASES, ids=lambda c: getattr(c, "__name__", "")
)
def test_proto_enum_fully_mapped(
    type_decorator: type[et._ProtoEnumType[int]], proto_enum: EnumTypeWrapper
) -> None:
    """Every non-sentinel proto value must have a DB StrEnum mapping (both directions)."""
    proto_values = _proto_nonzero_values(proto_enum)
    mapped = set(type_decorator._int_to_str.keys())

    missing = {proto_enum.Name(v) for v in proto_values - mapped}
    extra = mapped - proto_values
    assert not missing, f"{type_decorator.__name__} missing proto values: {missing}"
    assert not extra, f"{type_decorator.__name__} maps non-proto values: {extra}"

    # StrEnum member count matches the mapped value set (no orphan members).
    assert len(list(type_decorator._str_enum)) == len(proto_values)
    # _str_to_int is the exact inverse of _int_to_str.
    assert type_decorator._str_to_int == {v: k for k, v in type_decorator._int_to_str.items()}


LEDGER_ENUM_CASES: list[tuple[type, EnumTypeWrapper, str]] = [
    (ledger.SleeveType, ledger_pb2.SleeveType, "SLEEVE_TYPE_"),
    (ledger.SleeveStatus, ledger_pb2.SleeveStatus, "SLEEVE_STATUS_"),
    (ledger.LotSide, ledger_pb2.LotSide, "LOT_SIDE_"),
    (ledger.LedgerEventType, ledger_pb2.LedgerEventType, "LEDGER_EVENT_TYPE_"),
]


@pytest.mark.parametrize(
    "str_enum,proto_enum,prefix", LEDGER_ENUM_CASES, ids=lambda c: getattr(c, "__name__", "")
)
def test_ledger_strenum_matches_proto(
    str_enum: type, proto_enum: EnumTypeWrapper, prefix: str
) -> None:
    """Ledger StrEnums (VARCHAR-stored) must mirror the proto enum member set by name."""
    proto_names = {
        proto_enum.Name(v)[len(prefix) :]
        for v in proto_enum.values()
        if not proto_enum.Name(v).endswith("_UNSPECIFIED")
    }
    str_enum_names = {m.name for m in str_enum}
    assert str_enum_names == proto_names, (
        f"{str_enum.__name__} drift: missing={proto_names - str_enum_names} "
        f"extra={str_enum_names - proto_names}"
    )
    # Value convention: member value == lowercased member name.
    for member in str_enum:
        assert member.value == member.name.lower()


def test_session_status_is_intentional_execution_status_subset() -> None:
    """SessionStatusType deliberately remaps a subset of ExecutionStatus (not full parity)."""
    mapped = set(et.SessionStatusType._int_to_str.keys())
    execution_values = _proto_nonzero_values(common_pb2.ExecutionStatus)
    assert mapped < execution_values  # strict subset
    assert common_pb2.EXECUTION_STATUS_PENDING not in mapped  # PENDING has no session equivalent


def test_alert_condition_reconciliation_values_round_trip() -> None:
    """Regression: proto values 9/10 must survive the DB round-trip uncoerced."""
    td = et.AlertConditionTypeType()
    dialect = cast(Dialect, None)
    for proto_value, expected_str in (
        (notification_pb2.ALERT_CONDITION_TYPE_RECONCILIATION_DRIFT, "reconciliation_drift"),
        (notification_pb2.ALERT_CONDITION_TYPE_SLEEVE_FROZEN, "sleeve_frozen"),
    ):
        db_value = td.process_bind_param(proto_value, dialect)
        assert db_value == expected_str  # not silently coerced to "price_above"
        assert td.process_result_value(db_value, dialect) == proto_value
