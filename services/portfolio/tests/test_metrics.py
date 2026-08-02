"""Metrics adapter tests — the portfolio ledger runtime on unified telemetry.

The ``src.metrics`` helpers keep their original public surface but now record
through ``llamatrade_telemetry``. These tests assert against the rendered
Prometheus exposition (``get_metrics().decode()``) so they verify the real
exported series names/labels, not just that a method was called.

Counters are global and accumulate across tests, so each assertion measures the
*delta* a recorder produces rather than an absolute value.
"""

from __future__ import annotations

import re
from uuid import uuid4

from llamatrade_telemetry import get_metrics

from src.metrics import (
    LEDGER_STREAM_PENDING,
    record_drift,
    record_drift_action,
    record_ingest,
    record_projection_read,
    set_reconcile_stale_accounts,
)


def _sample(text: str, name: str, labels: str) -> float:
    """Return the value of the ``name`` sample carrying ``labels``, or 0.0 if absent.

    Matches on label *containment*, not equality: the OTel Prometheus exporter
    appends ``otel_scope_*`` labels whose presence varies by exporter version.
    """
    wanted = dict(re.findall(r'(\w+)="([^"]*)"', labels))
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        match = re.match(rf"{re.escape(name)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>\S+)$", line)
        if match is None:
            continue
        present = dict(re.findall(r'(\w+)="([^"]*)"', match.group("labels") or ""))
        if all(present.get(k) == v for k, v in wanted.items()):
            return float(match.group("value"))
    return 0.0


def test_record_ingest_increments_events_ingested() -> None:
    name = "llamatrade_ledger_events_ingested_total"
    labels = 'result="success"'
    before = _sample(get_metrics().decode(), name, labels)

    record_ingest("success")

    after = _sample(get_metrics().decode(), name, labels)
    assert after == before + 1.0


def test_record_drift_increments_reconciliation_drift_by_kind() -> None:
    name = "llamatrade_ledger_reconciliation_drift_total"
    labels = 'kind="qty_mismatch"'
    before = _sample(get_metrics().decode(), name, labels)

    record_drift("qty_mismatch")

    after = _sample(get_metrics().decode(), name, labels)
    assert after == before + 1.0


def test_record_drift_action_increments_drift_actions() -> None:
    name = "llamatrade_ledger_drift_actions_total"
    labels = 'action="adopted"'
    before = _sample(get_metrics().decode(), name, labels)

    record_drift_action("adopted")

    after = _sample(get_metrics().decode(), name, labels)
    assert after == before + 1.0


def test_record_drift_action_collapses_froze_suffix() -> None:
    """``froze:N`` collapses to a bounded ``froze`` label (no count cardinality)."""
    name = "llamatrade_ledger_drift_actions_total"
    labels = 'action="froze"'
    before = _sample(get_metrics().decode(), name, labels)

    record_drift_action("froze:3")

    text = get_metrics().decode()
    assert _sample(text, name, labels) == before + 1.0
    # The raw "froze:3" must never appear as its own series.
    assert 'action="froze:3"' not in text


def test_stream_pending_gauge_sets_consumer_lag_entries() -> None:
    name = "llamatrade_events_consumer_lag"
    labels = 'group="portfolio-ledger",stream="ledger:fills"'

    LEDGER_STREAM_PENDING.set(7)

    assert _sample(get_metrics().decode(), name, labels) == 7.0

    LEDGER_STREAM_PENDING.set(0)
    assert _sample(get_metrics().decode(), name, labels) == 0.0


def test_reconcile_stale_accounts_gauge_tracks_count() -> None:
    name = "llamatrade_ledger_reconcile_stale_accounts"

    set_reconcile_stale_accounts(3)
    assert _sample(get_metrics().decode(), name, "") == 3.0

    set_reconcile_stale_accounts(0)
    assert _sample(get_metrics().decode(), name, "") == 0.0


def test_projection_read_with_poison_events_increments_and_warns(caplog) -> None:
    """A degraded projection served on a read is counted and names the account."""
    name = "llamatrade_ledger_incomplete_projection_reads_total"
    account_id = uuid4()
    before = _sample(get_metrics().decode(), name, "")

    with caplog.at_level("WARNING", logger="src.metrics"):
        record_projection_read(account_id, poison_events=2)

    assert _sample(get_metrics().decode(), name, "") == before + 1.0
    assert any(str(account_id) in r.message and "INCOMPLETE" in r.message for r in caplog.records)


def test_projection_read_clean_is_noop(caplog) -> None:
    name = "llamatrade_ledger_incomplete_projection_reads_total"
    record_projection_read(uuid4(), poison_events=1)  # ensure the series exists
    before = _sample(get_metrics().decode(), name, "")
    caplog.clear()

    with caplog.at_level("WARNING", logger="src.metrics"):
        record_projection_read(uuid4(), poison_events=0)

    assert _sample(get_metrics().decode(), name, "") == before
    assert not caplog.records


def test_no_forbidden_labels_on_ledger_series() -> None:
    """The migrated series must not carry high-cardinality labels."""
    record_ingest("success")
    record_drift("dust")
    record_drift_action("observed")
    record_projection_read(uuid4(), poison_events=1)
    set_reconcile_stale_accounts(1)
    LEDGER_STREAM_PENDING.set(1)

    text = get_metrics().decode()
    ledger_lines = [
        line
        for line in text.splitlines()
        if line.startswith(("llamatrade_ledger_", "llamatrade_events_consumer_lag"))
    ]
    assert ledger_lines
    for forbidden in ("tenant_id", "session_id", "account_id", "sleeve_id", "symbol"):
        assert all(forbidden not in line for line in ledger_lines)
