"""Datetime and date conversion for the proto ``Timestamp`` wrapper.

``common_pb2.Timestamp`` carries seconds + nanos since the Unix epoch. Encoding
rejects naive datetimes so a caller never books a local-time instant as UTC by
accident; decoding always returns a UTC-aware value. The ``date_*`` variants map a
calendar date to and from the ``Timestamp`` fields that carry dates (e.g. a
backtest's ``start_date``/``end_date``), anchored at UTC midnight.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from llamatrade_proto.generated import common_pb2

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def to_proto_timestamp(value: datetime) -> common_pb2.Timestamp:
    """Encode a timezone-aware datetime as a proto ``Timestamp``.

    Raises:
        ValueError: if ``value`` is naive. A naive datetime has no defined instant,
            so encoding it would silently assume the caller's local zone.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("to_proto_timestamp requires a timezone-aware datetime")
    delta = value - _EPOCH
    return common_pb2.Timestamp(
        seconds=delta.days * 86400 + delta.seconds,
        nanos=delta.microseconds * 1000,
    )


def from_proto_timestamp(value: common_pb2.Timestamp) -> datetime:
    """Decode a proto ``Timestamp`` into a UTC-aware datetime."""
    return datetime.fromtimestamp(value.seconds, tz=UTC).replace(microsecond=value.nanos // 1000)


def date_to_proto_timestamp(value: date) -> common_pb2.Timestamp:
    """Encode a calendar date as a proto ``Timestamp`` at UTC midnight.

    ``datetime`` is a ``date`` subclass; pass one to :func:`to_proto_timestamp`
    instead, so its time-of-day and timezone are preserved rather than dropped.
    """
    return to_proto_timestamp(datetime.combine(value, time.min, tzinfo=UTC))


def date_from_proto_timestamp(value: common_pb2.Timestamp) -> date:
    """Decode a proto ``Timestamp`` into the UTC calendar date it falls on."""
    return from_proto_timestamp(value).date()
