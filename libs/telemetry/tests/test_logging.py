from __future__ import annotations

import json
import logging
import sys

import pytest

from llamatrade_telemetry import tracing
from llamatrade_telemetry.logging import (
    _LOGGER_WIDTH,
    ConsoleFormatter,
    ContextFilter,
    DedupeFilter,
    JSONFormatter,
    LogContext,
    _logger_label,
    _short_path,
    clear_request_context,
    color_enabled,
    configure_logging,
    get_logger,
    mask_destination,
    set_request_context,
)


def _record(msg: str = "hi", level: int = logging.INFO, **extra: object) -> logging.LogRecord:
    rec = logging.LogRecord("test", level, __file__, 10, msg, None, None)
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


def _json(record: logging.LogRecord, **kwargs: str) -> dict[str, object]:
    formatted = JSONFormatter(kwargs.pop("service", "svc"), kwargs.pop("project_id", None)).format(
        record
    )
    parsed: dict[str, object] = json.loads(formatted)
    return parsed


@pytest.fixture(autouse=True)
def _clean_context() -> object:
    clear_request_context()
    yield
    clear_request_context()


# --------------------------------------------------------------------------- #
# JSON renderer: Cloud Logging contract
# --------------------------------------------------------------------------- #
def test_basic_fields() -> None:
    out = _json(_record())
    assert out["service"] == "svc"
    assert out["severity"] == "INFO"
    assert out["message"] == "hi"
    assert out["logger"] == "test"
    assert str(out["time"]).endswith("Z")


@pytest.mark.parametrize(
    ("levelno", "expected"),
    [
        (logging.DEBUG, "DEBUG"),
        (logging.INFO, "INFO"),
        (logging.WARNING, "WARNING"),
        (logging.ERROR, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
        (logging.NOTSET, "DEFAULT"),
        (45, "ERROR"),
    ],
)
def test_severity_matches_cloud_logging_names(levelno: int, expected: str) -> None:
    assert _json(_record(level=levelno))["severity"] == expected


def test_timestamp_comes_from_record_not_format_time() -> None:
    rec = _record()
    rec.created = 1_600_000_000.0
    assert _json(rec)["time"] == "2020-09-13T12:26:40Z"


def test_source_location_is_repo_relative_with_string_line() -> None:
    location = _json(_record())["logging.googleapis.com/sourceLocation"]
    assert isinstance(location, dict)
    # int64 in the LogEntry proto renders as a JSON string.
    assert location["line"] == "10"
    assert not str(location["file"]).startswith("/")


def test_trace_fields_use_resource_name_when_project_known() -> None:
    with tracing.span("op"):
        out = _json(_record(), project_id="my-proj")
    trace_field = str(out["logging.googleapis.com/trace"])
    assert trace_field.startswith("projects/my-proj/traces/")
    assert len(trace_field.rsplit("/", 1)[1]) == 32
    assert len(str(out["logging.googleapis.com/spanId"])) == 16
    assert isinstance(out["logging.googleapis.com/trace_sampled"], bool)


def test_trace_field_is_bare_id_without_a_project() -> None:
    with tracing.span("op"):
        out = _json(_record())
    assert len(str(out["logging.googleapis.com/trace"])) == 32


def test_no_trace_fields_outside_a_span() -> None:
    assert "logging.googleapis.com/trace" not in _json(_record())


def test_exception_lands_in_stack_trace_for_error_reporting() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "err", None, sys.exc_info())
    out = _json(rec)
    assert "boom" in str(out["stack_trace"])
    assert "Traceback" in str(out["stack_trace"])


def test_request_context_promoted_to_top_level() -> None:
    set_request_context(request_id="r1", tenant_id="t1", user_id="u1")
    out = _json(_record())
    assert out["request_id"] == "r1"
    assert out["tenant_id"] == "t1"
    assert out["user_id"] == "u1"


def test_domain_fields_are_flat_and_queryable() -> None:
    out = _json(_record(client_order_id="coid-1", symbol="AAPL"))
    assert out["client_order_id"] == "coid-1"
    assert out["symbol"] == "AAPL"


def test_domain_field_cannot_clobber_a_reserved_key() -> None:
    out = _json(_record(service="attacker", severity="DEBUG"))
    assert out["service"] == "svc"
    assert out["severity"] == "INFO"


# --------------------------------------------------------------------------- #
# LogContext
# --------------------------------------------------------------------------- #
def test_logcontext_scopes_domain_fields() -> None:
    with LogContext(symbol="AAPL"):
        assert _json(_record())["symbol"] == "AAPL"
    assert "symbol" not in _json(_record())


def test_logcontext_promotes_identity_keys() -> None:
    with LogContext(tenant_id="t9", execution_id="e1"):
        out = _json(_record())
        assert out["tenant_id"] == "t9"
        assert out["execution_id"] == "e1"
    assert "tenant_id" not in _json(_record())


def test_logcontext_nests_and_restores_exactly() -> None:
    with LogContext(tenant_id="outer", symbol="AAPL"):
        with LogContext(tenant_id="inner", side="buy"):
            out = _json(_record())
            assert out["tenant_id"] == "inner"
            assert out["symbol"] == "AAPL"
            assert out["side"] == "buy"
        restored = _json(_record())
        assert restored["tenant_id"] == "outer"
        assert "side" not in restored


def test_call_site_extra_wins_over_bound_field() -> None:
    with LogContext(symbol="AAPL"):
        assert _json(_record(symbol="TSLA"))["symbol"] == "TSLA"


def test_logcontext_ignores_none_identity() -> None:
    with LogContext(tenant_id=None):
        assert "tenant_id" not in _json(_record())


# --------------------------------------------------------------------------- #
# Console renderer
# --------------------------------------------------------------------------- #
def test_console_line_is_scannable_without_color() -> None:
    line = ConsoleFormatter("svc", color=False).format(_record("Session started"))
    assert "\x1b[" not in line
    assert "INFO" in line
    assert "Session started" in line


def test_console_renders_fields_and_identity() -> None:
    set_request_context(tenant_id="t1")
    with LogContext(client_order_id="coid-1"):
        line = ConsoleFormatter(color=False).format(_record("Submitting"))
    assert "client_order_id=coid-1" in line
    assert "tenant_id=t1" in line


def test_console_abbreviates_uuids_but_json_keeps_them_whole() -> None:
    tenant = "9c1f4a80-1d2e-4f11-9a77-2b3c4d5e6f70"
    record = _record("x", sleeve_id=tenant)
    line = ConsoleFormatter(color=False).format(record)
    assert "sleeve_id=9c1f4a80…" in line
    assert _json(_record("x", sleeve_id=tenant))["sleeve_id"] == tenant


def test_console_leaves_non_uuid_values_intact() -> None:
    line = ConsoleFormatter(color=False).format(_record("x", client_order_id="lt-8f21c4de"))
    assert "client_order_id=lt-8f21c4de" in line


def test_console_quotes_values_with_spaces() -> None:
    line = ConsoleFormatter(color=False).format(_record("x", reason="no active subscription"))
    assert 'reason="no active subscription"' in line


def test_console_indents_traceback_instead_of_escaping_it() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "err", None, sys.exc_info())
    line = ConsoleFormatter(color=False).format(rec)
    body = line.split("\n", 1)[1]
    assert "\\n" not in line
    assert body.startswith("    ")
    assert "ValueError: boom" in body


def test_console_colorizes_when_enabled() -> None:
    line = ConsoleFormatter(color=True).format(_record("x", level=logging.ERROR))
    assert "\x1b[" in line


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("src.recovery", "recovery"),
        ("llamatrade_alpaca.streaming.base", "alpaca.streaming.base"),
        ("src.tasks.reconciliation", "tasks.reconciliation"),
    ],
)
def test_logger_label_strips_boilerplate(name: str, expected: str) -> None:
    _logger_label.cache_clear()
    assert _logger_label(name) == expected


def test_logger_label_abbreviates_overlong_names() -> None:
    _logger_label.cache_clear()
    label = _logger_label("alpha.beta.gamma.delta.epsilon.zeta_module_name")
    assert len(label) <= _LOGGER_WIDTH


def test_color_enabled_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert color_enabled("always") is True
    assert color_enabled("never") is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert color_enabled("auto") is False


def test_short_path_trims_site_packages() -> None:
    _short_path.cache_clear()
    assert _short_path("/usr/lib/python3.14/site-packages/pkg/mod.py") == "pkg/mod.py"


@pytest.mark.parametrize(
    ("absolute", "expected"),
    [
        # Same depth-independent answer whatever the process was launched from.
        ("/app/src/recovery.py", "src/recovery.py"),
        ("/app/src/streaming/publisher.py", "src/streaming/publisher.py"),
        ("/opt/checkout/services/trading/src/main.py", "services/trading/src/main.py"),
        (
            "/opt/checkout/libs/telemetry/llamatrade_telemetry/logging.py",
            "libs/telemetry/llamatrade_telemetry/logging.py",
        ),
    ],
)
def test_short_path_cuts_at_a_source_root_when_outside_the_cwd(
    absolute: str, expected: str
) -> None:
    _short_path.cache_clear()
    assert _short_path(absolute) == expected


# --------------------------------------------------------------------------- #
# Flood control
# --------------------------------------------------------------------------- #
class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_dedupe_passes_burst_then_suppresses() -> None:
    clock = _Clock()
    filt = DedupeFilter(window=60.0, burst=3, clock=clock)
    passed = [filt.filter(_record("same", level=logging.WARNING)) for _ in range(10)]
    assert passed[:3] == [True, True, True]
    assert not any(passed[3:])


def test_dedupe_reports_the_suppressed_count_next_window() -> None:
    clock = _Clock()
    filt = DedupeFilter(window=60.0, burst=1, clock=clock)
    for _ in range(5):
        filt.filter(_record("same", level=logging.WARNING))
    clock.now = 61.0
    record = _record("same", level=logging.WARNING)
    assert filt.filter(record) is True
    assert "+4 identical suppressed" in record.getMessage()
    assert record.suppressed_repeats == 4


def test_dedupe_keys_on_rendered_text_so_distinct_orders_survive() -> None:
    clock = _Clock()
    filt = DedupeFilter(window=60.0, burst=1, clock=clock)
    records = [
        logging.LogRecord("t", logging.WARNING, __file__, 1, "Order %s failed", (f"o{i}",), None)
        for i in range(5)
    ]
    assert all(filt.filter(rec) for rec in records)


def test_dedupe_exempts_debug() -> None:
    clock = _Clock()
    filt = DedupeFilter(window=60.0, burst=1, clock=clock)
    assert all(filt.filter(_record("same", level=logging.DEBUG)) for _ in range(10))


def test_dedupe_never_raises_on_a_malformed_format_string() -> None:
    """A filter that raises escapes logging's handleError and hits the caller."""
    clock = _Clock()
    filt = DedupeFilter(window=60.0, burst=1, clock=clock)
    record = logging.LogRecord("t", logging.WARNING, __file__, 1, "progress %d%%", ("nope",), None)
    assert filt.filter(record) is True


def test_a_bad_format_string_does_not_propagate_to_the_caller() -> None:
    configure_logging("svc", "INFO", fmt="json")
    get_logger("t").info("progress %d%%", "nope")


def test_dedupe_memory_is_bounded() -> None:
    clock = _Clock()
    filt = DedupeFilter(window=60.0, burst=1, capacity=4, clock=clock)
    for i in range(20):
        filt.filter(_record(f"msg-{i}", level=logging.WARNING))
    assert len(filt._seen) <= 4


# --------------------------------------------------------------------------- #
# configure_logging
# --------------------------------------------------------------------------- #
def test_configure_logging_selects_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_logging("svc", "DEBUG", fmt="console", color="never")
    assert isinstance(logging.getLogger().handlers[0].formatter, ConsoleFormatter)
    configure_logging("svc", "INFO", fmt="json")
    assert isinstance(logging.getLogger().handlers[0].formatter, JSONFormatter)
    get_logger("x").info("ok")


def test_configure_logging_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("LOG_COLOR", "never")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging("svc")
    assert isinstance(logging.getLogger().handlers[0].formatter, ConsoleFormatter)
    assert logging.getLogger().level == logging.WARNING
    configure_logging("svc", "INFO", fmt="json")


def test_configure_logging_attaches_flood_control() -> None:
    configure_logging("svc", "INFO", fmt="json")
    handler = logging.getLogger().handlers[0]
    assert any(isinstance(f, DedupeFilter) for f in handler.filters)
    configure_logging("svc", "INFO", fmt="json", dedupe=False)
    assert not any(isinstance(f, DedupeFilter) for f in logging.getLogger().handlers[0].filters)
    configure_logging("svc", "INFO", fmt="json")


def test_configure_logging_quiets_chatty_third_parties() -> None:
    configure_logging("svc", "INFO", fmt="json")
    assert logging.getLogger("aiokafka.consumer.group_coordinator").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


def test_configure_logging_reclaims_hijacked_loggers() -> None:
    """uvicorn installs its own stderr handler and stops propagating."""
    hijacked = logging.getLogger("uvicorn.error")
    hijacked.addHandler(logging.StreamHandler())
    hijacked.propagate = False

    configure_logging("svc", "INFO", fmt="json")

    assert hijacked.handlers == []
    assert hijacked.propagate is True


def test_configure_logging_attaches_the_context_filter() -> None:
    configure_logging("svc", "INFO", fmt="json")
    handler = logging.getLogger().handlers[0]
    # On the handler, not the logger: logger filters never see propagated records.
    assert any(isinstance(f, ContextFilter) for f in handler.filters)


# --------------------------------------------------------------------------- #
# ContextFilter: the same fields must reach every handler, not just the formatter
# --------------------------------------------------------------------------- #
def test_context_filter_stamps_bound_fields_onto_the_record() -> None:
    filt = ContextFilter()
    with LogContext(tenant_id="t1", client_order_id="coid-1"):
        record = _record()
        assert filt.filter(record) is True
        assert record.tenant_id == "t1"
        assert record.client_order_id == "coid-1"


def test_context_filter_never_overwrites_an_explicit_extra() -> None:
    filt = ContextFilter()
    with LogContext(tenant_id="bound", symbol="AAPL"):
        record = _record(tenant_id="explicit", symbol="TSLA")
        filt.filter(record)
        assert record.tenant_id == "explicit"
        assert record.symbol == "TSLA"
        out = _json(record)
        assert out["tenant_id"] == "explicit"
        assert out["symbol"] == "TSLA"


def test_identity_is_not_duplicated_into_domain_fields() -> None:
    filt = ContextFilter()
    with LogContext(tenant_id="t1"):
        record = _record()
        filt.filter(record)
        line = ConsoleFormatter(color=False).format(record)
    assert line.count("tenant_id=t1") == 1


# --------------------------------------------------------------------------- #
# Destination masking
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("naib@example.com", "n…@example.com"),
        ("+15551234567", "…4567"),
        ("12", "…"),
        ("", ""),
    ],
)
def test_mask_destination(raw: str, expected: str) -> None:
    assert mask_destination(raw) == expected


# --------------------------------------------------------------------------- #
# Cross-service correlation
# --------------------------------------------------------------------------- #
def test_console_carries_a_trace_marker_for_local_grepping() -> None:
    with tracing.span("op"):
        line = ConsoleFormatter(color=False).format(_record("x"))
        expected = format(tracing.trace.get_current_span().get_span_context().trace_id, "032x")[:8]
    assert f"trace={expected}" in line


def test_console_has_no_trace_marker_outside_a_span() -> None:
    assert "trace=" not in ConsoleFormatter(color=False).format(_record("x"))
