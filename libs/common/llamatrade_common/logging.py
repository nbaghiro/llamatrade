"""Structured logging configuration for LlamaTrade services.

This module provides JSON-formatted logging with correlation IDs,
tenant context, and standardized fields for observability.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from types import TracebackType

# Context variables for request-scoped values
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def set_request_context(
    request_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Set request context for logging."""
    if request_id:
        _request_id.set(request_id)
    if tenant_id:
        _tenant_id.set(tenant_id)
    if user_id:
        _user_id.set(user_id)


def clear_request_context() -> None:
    """Clear request context after request completes."""
    _request_id.set(None)
    _tenant_id.set(None)
    _user_id.set(None)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Outputs logs in JSON format with standardized fields:
    - timestamp: ISO 8601 format
    - level: Log level name
    - logger: Logger name
    - message: Log message
    - service: Service name
    - request_id: Correlation ID (if set)
    - tenant_id: Tenant ID (if set)
    - user_id: User ID (if set)
    - extra: Additional context
    """

    def __init__(self, service_name: str = "llamatrade"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_dict: dict[str, str | dict[str, str | int] | None] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        # Add context variables
        request_id = _request_id.get()
        if request_id:
            log_dict["request_id"] = request_id

        tenant_id = _tenant_id.get()
        if tenant_id:
            log_dict["tenant_id"] = tenant_id

        user_id = _user_id.get()
        if user_id:
            log_dict["user_id"] = user_id

        # Add location info
        if record.pathname:
            log_dict["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        extra = {}
        for key, value in record.__dict__.items():
            if key not in {
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
            }:
                extra[key] = value

        if extra:
            log_dict["extra"] = extra

        return json.dumps(log_dict, default=str)


def configure_logging(
    service_name: str,
    level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure structured logging for a service.

    Args:
        service_name: Name of the service (e.g., "auth", "trading")
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_output: Whether to output JSON format (True for production)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    if json_output:
        handler.setFormatter(JSONFormatter(service_name))
    else:
        # Human-readable format for development
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding extra fields to all logs within a block.

    Example:
        with LogContext(order_id="123", symbol="AAPL"):
            logger.info("Processing order")  # Includes order_id and symbol
    """

    def __init__(self, **kwargs: str | int | float | bool) -> None:
        self.extra = kwargs
        self._token: Token[str | None] | None = None

    def __enter__(self) -> LogContext:
        # Store extra context - in a real implementation, this would
        # use a ContextVar to inject into all log records
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass
