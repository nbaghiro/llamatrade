"""Structured logging with request, trace, and domain-field correlation.

One record renders two ways: a colorized console line for local work
(``LOG_FORMAT=console``) and Cloud Logging-native JSON for deployment
(``LOG_FORMAT=json``). Fields bound with :class:`LogContext` ride every record
emitted inside the block, so background paths carry the same identifiers a
request does.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from types import TracebackType

from opentelemetry import trace

# Request-scoped context (async-safe).
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_extra: ContextVar[dict[str, object] | None] = ContextVar("log_extra", default=None)

_IDENTITY_VARS: dict[str, ContextVar[str | None]] = {
    "request_id": _request_id,
    "tenant_id": _tenant_id,
    "user_id": _user_id,
}

_RESERVED_RECORD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "asctime",
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

# Third-party loggers whose INFO chatter drowns application logs.
_QUIET_LOGGERS = {
    "uvicorn.access": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    "asyncio": logging.WARNING,
    "aiokafka.cluster": logging.WARNING,
    "aiokafka.conn": logging.WARNING,
    "aiokafka.consumer.group_coordinator": logging.WARNING,
    "aiokafka.consumer.subscription_state": logging.WARNING,
    "kafka.conn": logging.WARNING,
    "websockets.client": logging.WARNING,
    "stripe": logging.WARNING,
}

# Loggers that install their own handler and stop propagating, which would keep
# their records (uvicorn's startup and error lines especially) out of the shared
# format entirely. Reclaimed so every line in the process renders the same way.
_RECLAIMED_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "celery.task",
    "celery.redirected",
)

_CONSOLE_FORMATS = frozenset({"console", "text", "pretty", "human"})

_CWD = os.getcwd()

# Directory names that begin a repo-relative source path.
_SOURCE_ROOTS = frozenset({"src", "libs", "services"})


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


def current_request_id() -> str | None:
    """The request id bound to this task, for forwarding across a service hop."""
    return _request_id.get()


def _identity() -> dict[str, str]:
    """Correlation ids currently bound to this task."""
    out: dict[str, str] = {}
    for key, var in _IDENTITY_VARS.items():
        value = var.get()
        if value:
            out[key] = value
    return out


def _record_identity(record: logging.LogRecord) -> dict[str, str]:
    """Correlation ids for this record; an explicit ``extra=`` wins over the block."""
    out: dict[str, str] = {}
    for key, var in _IDENTITY_VARS.items():
        value = getattr(record, key, None) or var.get()
        if value:
            out[key] = str(value)
    return out


def _bound_fields(record: logging.LogRecord) -> dict[str, object]:
    """Domain fields for this record; a call-site ``extra=`` wins over the block.

    Identity keys are excluded: they render separately as correlation fields.
    """
    fields: dict[str, object] = {}
    ctx = _extra.get()
    if ctx:
        fields.update(ctx)
    for key, value in record.__dict__.items():
        if key not in _RESERVED_RECORD_KEYS and not key.startswith("_"):
            fields[key] = value
    for key in _IDENTITY_VARS:
        fields.pop(key, None)
    return fields


class ContextFilter(logging.Filter):
    """Stamp bound context onto the record so every handler sees the same fields.

    The stdout formatters could read the ContextVars directly, but the OTLP
    handler builds its attributes from the record alone, so the merge has to
    happen on the record for both sinks to agree.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in _identity().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        for key, value in (_extra.get() or {}).items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def _trace_ids() -> tuple[str, str, bool] | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return (
            format(ctx.trace_id, "032x"),
            format(ctx.span_id, "016x"),
            ctx.trace_flags.sampled,
        )
    return None


def _severity(levelno: int) -> str:
    """Map a Python level onto a Cloud Logging severity."""
    if levelno >= logging.CRITICAL:
        return "CRITICAL"
    if levelno >= logging.ERROR:
        return "ERROR"
    if levelno >= logging.WARNING:
        return "WARNING"
    if levelno >= logging.INFO:
        return "INFO"
    if levelno >= logging.DEBUG:
        return "DEBUG"
    return "DEFAULT"


@lru_cache(maxsize=2048)
def _short_path(pathname: str) -> str:
    """Repo- or package-relative source path (absolute container paths are noise)."""
    marker = f"{os.sep}site-packages{os.sep}"
    if marker in pathname:
        return pathname.rsplit(marker, 1)[1]
    try:
        relative = os.path.relpath(pathname, _CWD)
    except ValueError:
        relative = pathname
    if not relative.startswith(os.pardir):
        return relative
    # Outside the working directory: cut at the outermost source root, so the
    # same file renders the same way whatever the process was launched from.
    parts = pathname.split(os.sep)
    for index, part in enumerate(parts):
        if part in _SOURCE_ROOTS:
            return os.sep.join(parts[index:])
    return os.sep.join(parts[-3:]) if len(parts) > 3 else pathname


def _timestamp(created: float) -> str:
    return datetime.fromtimestamp(created, UTC).isoformat().replace("+00:00", "Z")


class JSONFormatter(logging.Formatter):
    """Render a record as one Cloud Logging-native JSON line.

    Field names follow Google's structured-log contract (``severity``,
    ``logging.googleapis.com/*``, ``stack_trace``) so a GKE deployment gets
    severity filtering, trace links, source location, and Error Reporting
    grouping without a collector rule. Domain fields sit at the top level so
    they query as ``jsonPayload.client_order_id``.
    """

    def __init__(self, service_name: str = "llamatrade", project_id: str | None = None) -> None:
        super().__init__()
        self.service_name = service_name
        self.project_id = project_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "severity": _severity(record.levelno),
            "message": record.getMessage(),
            "time": _timestamp(record.created),
            "logger": record.name,
            "service": self.service_name,
        }
        payload.update(_record_identity(record))

        ids = _trace_ids()
        if ids is not None:
            trace_id, span_id, sampled = ids
            payload["logging.googleapis.com/trace"] = (
                f"projects/{self.project_id}/traces/{trace_id}" if self.project_id else trace_id
            )
            payload["logging.googleapis.com/spanId"] = span_id
            payload["logging.googleapis.com/trace_sampled"] = sampled

        if record.pathname:
            payload["logging.googleapis.com/sourceLocation"] = {
                "file": _short_path(record.pathname),
                "line": str(record.lineno),
                "function": record.funcName,
            }

        if record.exc_info:
            payload["stack_trace"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["stack_trace"] = record.exc_text
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        for key, value in _bound_fields(record).items():
            if key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


_ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "bright_red": "\033[91m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "grey": "\033[90m",
}

_LEVEL_STYLE = {
    "DEBUG": "grey",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "bright_red",
    "CRITICAL": "magenta",
    "DEFAULT": "grey",
}

_LEVEL_LABEL = {
    "DEBUG": "DEBG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERRO",
    "CRITICAL": "CRIT",
    "DEFAULT": "----",
}

# 28 leaves ~95% of this repo's logger names unabbreviated.
_LOGGER_WIDTH = 28


@lru_cache(maxsize=2048)
def _logger_label(name: str) -> str:
    """Shorten a dotted logger name to fit the console's fixed column."""
    label = name.removeprefix("src.").replace("llamatrade_", "")
    if len(label) <= _LOGGER_WIDTH:
        return label
    parts = label.split(".")
    while len(".".join(parts)) > _LOGGER_WIDTH:
        for index, part in enumerate(parts[:-1]):
            if len(part) > 1:
                parts[index] = part[0]
                break
        else:
            break
    label = ".".join(parts)
    return label if len(label) <= _LOGGER_WIDTH else "…" + label[-(_LOGGER_WIDTH - 1) :]


_UUID_LENGTH = 36
_UUID_DASHES = (8, 13, 18, 23)


def _is_uuid(text: str) -> bool:
    if len(text) != _UUID_LENGTH:
        return False
    return all(text[i] == "-" for i in _UUID_DASHES) and all(
        char in "0123456789abcdefABCDEF-" for char in text
    )


def _fmt_value(value: object) -> str:
    """Render a field for the console: UUIDs abbreviated, whitespace quoted.

    A full UUID per field crowds out the message; the first block stays unique
    enough to follow and to grep, and JSON keeps the whole value.
    """
    text = value if isinstance(value, str) else str(value)
    if _is_uuid(text):
        return f"{text[:8]}…"
    if not text or any(char.isspace() for char in text) or '"' in text:
        return json.dumps(text)
    return text


def color_enabled(mode: str) -> bool:
    """Resolve ``always``/``never``/``auto`` against the terminal and NO_COLOR."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


class ConsoleFormatter(logging.Formatter):
    """Render a record as one aligned, colorized line for a human reader.

    Layout is ``time level logger message fields``, with correlation ids last
    so the sentence stays at a fixed offset, and tracebacks indented beneath
    rather than escaped into the message.
    """

    def __init__(self, service_name: str = "llamatrade", *, color: bool = True) -> None:
        super().__init__()
        self.service_name = service_name
        self.color = color

    def _paint(self, text: str, *styles: str) -> str:
        if not self.color or not text:
            return text
        prefix = "".join(_ANSI[style] for style in styles)
        return f"{prefix}{text}{_ANSI['reset']}"

    def format(self, record: logging.LogRecord) -> str:
        severity = _severity(record.levelno)
        stamp = datetime.fromtimestamp(record.created, UTC).strftime("%H:%M:%S.%f")[:-3]
        level = _LEVEL_LABEL[severity]
        logger_label = _logger_label(record.name).ljust(_LOGGER_WIDTH)

        message = record.getMessage()
        head = " ".join(
            (
                self._paint(stamp, "grey"),
                self._paint(level, "bold", _LEVEL_STYLE[severity]),
                self._paint(logger_label, "grey"),
                message.replace("\n", "\n" + " " * 4),
            )
        )

        parts = [head]
        fields = _bound_fields(record)
        if fields:
            parts.append(self._render_fields(fields, "cyan"))
        identity = _record_identity(record)
        ids = _trace_ids()
        if ids is not None:
            # Enough to grep one flow across every service in the same stream;
            # the whole id is in the JSON and in Loki.
            identity = {"trace": ids[0][:8], **identity}
        if identity:
            parts.append(self._render_fields(identity, "grey"))

        line = "  ".join(parts)
        trailer = self._trailer(record)
        return f"{line}\n{trailer}" if trailer else line

    def _render_fields(self, fields: Mapping[str, object], style: str) -> str:
        rendered = [
            f"{self._paint(key, style)}{self._paint('=', 'grey')}{_fmt_value(value)}"
            for key, value in fields.items()
        ]
        return " ".join(rendered)

    def _trailer(self, record: logging.LogRecord) -> str:
        """Indented traceback and stack, kept off the message line."""
        blocks: list[str] = []
        if record.exc_info:
            blocks.append(self.formatException(record.exc_info))
        elif record.exc_text:
            blocks.append(record.exc_text)
        if record.stack_info:
            blocks.append(self.formatStack(record.stack_info))
        if not blocks:
            return ""
        body = "\n".join(blocks)
        indented = "\n".join(f"    {line}" for line in body.splitlines())
        return self._paint(indented, "red")


@dataclass
class _Repeat:
    first: float
    count: int
    suppressed: int


class DedupeFilter(logging.Filter):
    """Collapse identical repeating records so a hot loop cannot flood the log.

    The first ``burst`` copies of an identical rendered message pass through;
    further copies within ``window`` seconds are dropped and their count is
    appended to the next copy that passes. DEBUG is exempt, since raising the
    level is a deliberate request for everything.

    Keying on the rendered message (not the template) is what keeps this safe:
    a line naming a distinct order or symbol is a distinct key, so only genuinely
    identical repetition collapses. The window is sized above the periodic loop
    intervals (30s-300s) that produce most repetition.
    """

    def __init__(
        self,
        *,
        window: float = 300.0,
        burst: int = 3,
        capacity: int = 2048,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.window = window
        self.burst = burst
        self.capacity = capacity
        self._clock = clock
        self._lock = threading.Lock()
        self._seen: OrderedDict[tuple[str, int, str], _Repeat] = OrderedDict()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno <= logging.DEBUG:
            return True

        try:
            message = record.getMessage()
        except Exception:
            # A malformed format string is the formatter's to report through
            # handleError; a filter that raises would take down the caller.
            return True
        key = (record.name, record.levelno, message)
        now = self._clock()

        with self._lock:
            state = self._seen.get(key)
            if state is not None and now - state.first < self.window:
                state.count += 1
                if state.count <= self.burst:
                    return True
                state.suppressed += 1
                return False

            suppressed = state.suppressed if state is not None else 0
            self._seen[key] = _Repeat(first=now, count=1, suppressed=0)
            self._seen.move_to_end(key)
            while len(self._seen) > self.capacity:
                self._seen.popitem(last=False)

        if suppressed:
            record.msg = f"{message} (+{suppressed} identical suppressed)"
            record.args = None
            record.suppressed_repeats = suppressed
        return True


def resolve_level(level: str) -> int:
    """Map a level name to its number, defaulting to INFO for unknown names.

    A typo in ``LOG_LEVEL`` must never crash startup (the old
    ``getattr(logging, level.upper())`` raised ``AttributeError``).
    """
    return logging.getLevelNamesMapping().get(level.upper(), logging.INFO)


def configure_logging(
    service_name: str,
    level: str | None = None,
    *,
    fmt: str | None = None,
    color: str | None = None,
    dedupe: bool = True,
    project_id: str | None = None,
) -> None:
    """Install the root log handler for a service or worker.

    Omitted arguments fall back to the environment (``LOG_LEVEL``,
    ``LOG_FORMAT``, ``LOG_COLOR``, ``GOOGLE_CLOUD_PROJECT``) so standalone
    entry points behave like a service without wiring settings themselves.
    """
    resolved_level = level or os.environ.get("LOG_LEVEL", "INFO")
    resolved_fmt = (fmt or os.environ.get("LOG_FORMAT", "json")).lower()
    resolved_color = color or os.environ.get("LOG_COLOR", "auto")
    resolved_project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")

    level_no = resolve_level(resolved_level)
    root_logger = logging.getLogger()
    root_logger.setLevel(level_no)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(level_no)
    if resolved_fmt in _CONSOLE_FORMATS:
        stream.setFormatter(
            ConsoleFormatter(service_name, color=color_enabled(resolved_color.lower()))
        )
    else:
        stream.setFormatter(JSONFormatter(service_name, resolved_project))
    # On the handler, not the logger: a logger's filters never see records that
    # propagated up from a child.
    stream.addFilter(ContextFilter())
    if dedupe:
        stream.addFilter(DedupeFilter())
    root_logger.addHandler(stream)

    for name in _RECLAIMED_LOGGERS:
        reclaimed = logging.getLogger(name)
        reclaimed.handlers.clear()
        reclaimed.propagate = True

    for name, quiet_level in _QUIET_LOGGERS.items():
        logging.getLogger(name).setLevel(quiet_level)


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger; context + trace ids are injected by the formatter."""
    return logging.getLogger(name)


def mask_destination(value: str) -> str:
    """Render a delivery destination for logs: enough to correlate, not to identify."""
    if not value:
        return ""
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:1]}…@{domain}"
    digits = "".join(char for char in value if char.isdigit())
    return f"…{digits[-4:]}" if len(digits) >= 4 else "…"


class LogContext:
    """Bind fields to every log record emitted inside the block.

    ``request_id`` / ``tenant_id`` / ``user_id`` become top-level correlation
    fields; anything else rides alongside the message as a queryable field.
    Use it at a boundary (consumer, task, loop tick) so call sites inside stay
    unchanged.

    Example:
        with LogContext(tenant_id=tid, client_order_id=coid):
            logger.info("Submitting order")
    """

    def __init__(self, **fields: object) -> None:
        self._fields = fields
        self._identity: list[tuple[ContextVar[str | None], Token[str | None]]] = []
        self._extra_token: Token[dict[str, object] | None] | None = None

    def __enter__(self) -> LogContext:
        extra: dict[str, object] = {}
        for key, value in self._fields.items():
            var = _IDENTITY_VARS.get(key)
            if var is None:
                extra[key] = value
            elif value is not None:
                self._identity.append((var, var.set(str(value))))
        if extra:
            merged: dict[str, object] = {**(_extra.get() or {}), **extra}
            self._extra_token = _extra.set(merged)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._extra_token is not None:
            _extra.reset(self._extra_token)
            self._extra_token = None
        for var, token in reversed(self._identity):
            var.reset(token)
        self._identity.clear()
