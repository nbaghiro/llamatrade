"""Property tests for ``generate_deterministic_order_id`` (exactly-once submission key).

The id is the crash-recovery idempotency key sent to Alpaca as ``client_order_id``:
identical signals must always derive the identical id, any differing input must
derive a different one, equal instants must derive the same id regardless of the
timestamp's UTC offset, and the id must fit Alpaca's client_order_id limit.
"""

import re
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

from src.executor.order_executor import generate_deterministic_order_id

SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
OTHER_SESSION_ID = UUID("55555555-5555-5555-5555-555555555555")
SIGNAL_TS = datetime(2026, 7, 20, 15, 30, 0, tzinfo=UTC)

# Alpaca caps client_order_id at 48 characters; "lt-" + 16 hex chars = 19.
ALPACA_CLIENT_ORDER_ID_MAX = 48
ID_PATTERN = re.compile(r"^lt-[0-9a-f]{16}$")


def _generate(
    session_id: UUID = SESSION_ID,
    symbol: str = "AAPL",
    side: str = "buy",
    signal_timestamp: datetime = SIGNAL_TS,
) -> str:
    return generate_deterministic_order_id(
        session_id=session_id,
        symbol=symbol,
        side=side,
        signal_timestamp=signal_timestamp,
    )


class TestDeterministicOrderId:
    def test_identical_inputs_yield_identical_id_across_calls(self) -> None:
        ids = {_generate() for _ in range(10)}
        assert len(ids) == 1

    def test_format_is_lt_prefix_plus_16_hex(self) -> None:
        order_id = _generate()
        assert ID_PATTERN.fullmatch(order_id) is not None
        assert order_id.startswith("lt-")

    def test_length_fits_alpaca_client_order_id_limit(self) -> None:
        order_id = _generate()
        assert len(order_id) == 19  # "lt-" + 16 hex chars
        assert len(order_id) <= ALPACA_CLIENT_ORDER_ID_MAX

    def test_any_single_differing_input_changes_the_id(self) -> None:
        base = _generate()
        variants = [
            _generate(session_id=OTHER_SESSION_ID),
            _generate(symbol="MSFT"),
            _generate(side="sell"),
            _generate(signal_timestamp=SIGNAL_TS + timedelta(minutes=1)),
        ]
        assert len({base, *variants}) == 5

    def test_microsecond_timestamp_difference_changes_the_id(self) -> None:
        base = _generate()
        shifted = _generate(signal_timestamp=SIGNAL_TS + timedelta(microseconds=1))
        assert base != shifted

    def test_timezone_aware_timestamp_is_stable(self) -> None:
        first = _generate(signal_timestamp=datetime(2026, 7, 20, 15, 30, tzinfo=UTC))
        second = _generate(signal_timestamp=datetime(2026, 7, 20, 15, 30, tzinfo=UTC))
        assert first == second

    def test_equal_instants_in_different_offsets_derive_the_same_id(self) -> None:
        """The derivation normalizes an aware timestamp to UTC, so the same
        instant expressed in another offset derives the same key."""
        utc_ts = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
        for offset_hours in (-5, 5, 9, -11):
            offset_ts = utc_ts.astimezone(timezone(timedelta(hours=offset_hours)))
            assert utc_ts == offset_ts  # same instant
            assert _generate(signal_timestamp=utc_ts) == _generate(signal_timestamp=offset_ts)

    def test_utc_input_ids_are_byte_identical_to_the_established_key(self) -> None:
        """The id is the platform-wide idempotency key: these values are what
        UTC inputs have always hashed to and must never change."""
        assert _generate(signal_timestamp=SIGNAL_TS) == "lt-3f0952c96536468b"
        assert (
            _generate(signal_timestamp=datetime(2026, 7, 20, 15, 30, 0, 123456, tzinfo=UTC))
            == "lt-e5d626dbffb40039"
        )

    def test_naive_timestamp_is_hashed_as_given(self) -> None:
        """A naive timestamp is read as UTC wall clock and hashed verbatim, so
        its key is unchanged (and distinct from the aware-UTC key)."""
        naive_ts = datetime(2026, 7, 20, 15, 30)
        assert _generate(signal_timestamp=naive_ts) == "lt-6657dd885bd56a1e"
        assert _generate(signal_timestamp=naive_ts) != _generate(signal_timestamp=SIGNAL_TS)

    def test_symbol_and_side_are_hashed_verbatim(self) -> None:
        """Case is significant: submit_order uppercases the symbol and stringifies
        the side BEFORE deriving, so any drift there would silently fork the key."""
        assert _generate(symbol="AAPL") != _generate(symbol="aapl")
        assert _generate(side="buy") != _generate(side="BUY")
