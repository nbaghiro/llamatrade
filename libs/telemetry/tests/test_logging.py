from __future__ import annotations

import json
import logging
import sys

from llamatrade_telemetry import tracing
from llamatrade_telemetry.logging import (
    JSONFormatter,
    LogContext,
    clear_request_context,
    configure_logging,
    get_logger,
    set_request_context,
)


def _record(msg: str = "hi", **extra: object) -> logging.LogRecord:
    rec = logging.LogRecord("test", logging.INFO, __file__, 10, msg, None, None)
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


def test_basic_fields() -> None:
    out = json.loads(JSONFormatter("svc").format(_record()))
    assert out["service"] == "svc"
    assert out["level"] == "INFO"
    assert out["message"] == "hi"
    assert out["logger"] == "test"
    assert out["location"]["line"] == 10


def test_request_context_included() -> None:
    set_request_context(request_id="r1", tenant_id="t1", user_id="u1")
    try:
        out = json.loads(JSONFormatter("svc").format(_record()))
        assert out["request_id"] == "r1"
        assert out["tenant_id"] == "t1"
        assert out["user_id"] == "u1"
    finally:
        clear_request_context()


def test_record_extra_fields() -> None:
    out = json.loads(JSONFormatter("svc").format(_record(order_id="o1")))
    assert out["extra"]["order_id"] == "o1"


def test_logcontext_scopes_extra() -> None:
    with LogContext(symbol="AAPL"):
        out = json.loads(JSONFormatter("svc").format(_record()))
        assert out["extra"]["symbol"] == "AAPL"
    after = json.loads(JSONFormatter("svc").format(_record()))
    assert "symbol" not in after.get("extra", {})


def test_trace_ids_injected_within_span() -> None:
    with tracing.span("op"):
        out = json.loads(JSONFormatter("svc").format(_record()))
        assert len(out["trace_id"]) == 32
        assert len(out["span_id"]) == 16


def test_exception_formatted() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "err", None, sys.exc_info())
    out = json.loads(JSONFormatter().format(rec))
    assert "boom" in out["exception"]


def test_configure_logging_json_and_text() -> None:
    configure_logging("svc", "DEBUG", json_output=True)
    configure_logging("svc", "INFO", json_output=False)
    get_logger("x").info("ok")  # should not raise
