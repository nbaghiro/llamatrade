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

from llamatrade_telemetry import get_metrics

from src.metrics import (
    LEDGER_STREAM_PENDING,
    record_drift,
    record_drift_action,
    record_ingest,
)


def _sample(text: str, name: str, labels: str) -> float:
    """Return the current value of ``name{labels}`` in the exposition, or 0.0."""
    pattern = re.compile(rf"^{re.escape(name)}\{{{re.escape(labels)}\}} (\S+)$", re.MULTILINE)
    match = pattern.search(text)
    return float(match.group(1)) if match else 0.0


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
    name = "events_consumer_lag"
    labels = 'group="portfolio-ledger",stream="ledger:fills"'

    LEDGER_STREAM_PENDING.set(7)

    assert _sample(get_metrics().decode(), name, labels) == 7.0

    LEDGER_STREAM_PENDING.set(0)
    assert _sample(get_metrics().decode(), name, labels) == 0.0


def test_no_forbidden_labels_on_ledger_series() -> None:
    """The migrated series must not carry high-cardinality labels."""
    record_ingest("success")
    record_drift("dust")
    record_drift_action("observed")
    LEDGER_STREAM_PENDING.set(1)

    text = get_metrics().decode()
    ledger_lines = [
        line
        for line in text.splitlines()
        if line.startswith(("llamatrade_ledger_", "events_consumer_lag"))
    ]
    assert ledger_lines
    for forbidden in ("tenant_id", "session_id", "account_id", "sleeve_id", "symbol"):
        assert all(forbidden not in line for line in ledger_lines)
