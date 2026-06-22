"""Structured JSON logging with request + trace correlation.

Ported from ``llamatrade_common.logging`` and extended to inject ``trace_id`` /
``span_id`` from the active OpenTelemetry span, so a log line links to its trace.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from types import TracebackType

from opentelemetry import trace

# Request-scoped context (async-safe).
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_extra: ContextVar[dict[str, object] | None] = ContextVar("log_extra", default=None)

_RESERVED_RECORD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "thread",
        "threadName",
        "taskName",
        "message",
    }
)


def set_request_context(
    request_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Set request context for logging (called by the HTTP middleware)."""
    if request_id:
        _request_id.set(request_id)
    if tenant_id:
        _tenant_id.set(tenant_id)
    if user_id:
        _user_id.set(user_id)


def clear_request_context() -> None:
    """Clear request context after a request completes."""
    _request_id.set(None)
    _tenant_id.set(None)
    _user_id.set(None)
    _extra.set(None)


def _trace_ids() -> tuple[str, str] | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    return None


class JSONFormatter(logging.Formatter):
    """Format a log record as a single JSON line with standard fields."""

    def __init__(self, service_name: str = "llamatrade") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_dict: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        request_id = _request_id.get()
        if request_id:
            log_dict["request_id"] = request_id
        tenant_id = _tenant_id.get()
        if tenant_id:
            log_dict["tenant_id"] = tenant_id
        user_id = _user_id.get()
        if user_id:
            log_dict["user_id"] = user_id

        ids = _trace_ids()
        if ids is not None:
            log_dict["trace_id"], log_dict["span_id"] = ids

        if record.pathname:
            log_dict["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        extra: dict[str, object] = {}
        ctx_extra = _extra.get()
        if ctx_extra:
            extra.update(ctx_extra)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS:
                extra[key] = value
        if extra:
            log_dict["extra"] = extra

        return json.dumps(log_dict, default=str)


def _resolve_level(level: str) -> int:
    """Map a level name to its number, defaulting to INFO for unknown names.

    A typo in ``LOG_LEVEL`` must never crash startup (the old
    ``getattr(logging, level.upper())`` raised ``AttributeError``).
    """
    return logging.getLevelNamesMapping().get(level.upper(), logging.INFO)


def configure_logging(
    service_name: str,
    level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure root logging for a service (JSON for prod, text for dev)."""
    level_no = _resolve_level(level)
    root_logger = logging.getLogger()
    root_logger.setLevel(level_no)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level_no)
    if json_output:
        handler.setFormatter(JSONFormatter(service_name))
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger; context + trace ids are injected by the formatter."""
    return logging.getLogger(name)


class LogContext:
    """Add extra fields to every log within the block.

    Example:
        with LogContext(order_id="123", symbol="AAPL"):
            logger.info("processing")  # both fields appear under "extra"
    """

    def __init__(self, **kwargs: object) -> None:
        self.extra = kwargs
        self._token: Token[dict[str, object] | None] | None = None

    def __enter__(self) -> LogContext:
        current = _extra.get() or {}
        merged: dict[str, object] = {**current, **self.extra}
        self._token = _extra.set(merged)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _extra.reset(self._token)
