"""Tests for structured logging utilities."""

import json
import logging

import pytest

from llamatrade_common.logging import (
    JSONFormatter,
    LogContext,
    clear_request_context,
    configure_logging,
    get_logger,
    set_request_context,
)


class TestRequestContext:
    """Tests for request context management."""

    def teardown_method(self):
        """Clear context after each test."""
        clear_request_context()

    def test_set_request_context(self):
        """Test setting request context."""
        set_request_context(
            request_id="req-123",
            tenant_id="tenant-456",
            user_id="user-789",
        )
        # Context is set internally via ContextVar
        # We verify it works through JSONFormatter output

    def test_clear_request_context(self):
        """Test clearing request context."""
        set_request_context(request_id="req-123")
        clear_request_context()
        # Context is cleared

    def test_partial_context(self):
        """Test setting partial context."""
        set_request_context(request_id="req-123")
        # Only request_id is set


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    @pytest.fixture
    def formatter(self):
        """Create a JSON formatter."""
        return JSONFormatter(service_name="test-service")

    @pytest.fixture
    def log_record(self):
        """Create a log record."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        return record

    def test_format_basic(self, formatter, log_record):
        """Test basic log formatting."""
        output = formatter.format(log_record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert data["service"] == "test-service"
        assert "timestamp" in data

    def test_format_includes_location(self, formatter, log_record):
        """Test that location info is included."""
        output = formatter.format(log_record)
        data = json.loads(output)

        assert "location" in data
        assert data["location"]["file"] == "/path/to/file.py"
        assert data["location"]["line"] == 42

    def test_format_with_request_context(self, formatter, log_record):
        """Test formatting with request context."""
        set_request_context(
            request_id="req-123",
            tenant_id="tenant-456",
            user_id="user-789",
        )

        output = formatter.format(log_record)
        data = json.loads(output)

        assert data["request_id"] == "req-123"
        assert data["tenant_id"] == "tenant-456"
        assert data["user_id"] == "user-789"

        clear_request_context()

    def test_format_with_exception(self, formatter):
        """Test formatting with exception info."""
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "Test error" in data["exception"]


class TestConfigureLogging:
    """Tests for logging configuration."""

    def test_configure_json_logging(self):
        """Test configuring JSON logging."""
        configure_logging(
            service_name="test-service",
            level="DEBUG",
            json_output=True,
        )

        logger = logging.getLogger()
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_configure_human_readable_logging(self):
        """Test configuring human-readable logging."""
        configure_logging(
            service_name="test-service",
            level="INFO",
            json_output=False,
        )

        logger = logging.getLogger()
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
        # Human-readable formatter is standard Formatter
        assert not isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_configure_removes_existing_handlers(self):
        """Test that configuring removes existing handlers."""
        logger = logging.getLogger()
        logger.addHandler(logging.StreamHandler())
        logger.addHandler(logging.StreamHandler())
        assert len(logger.handlers) >= 2  # Verify we added handlers

        configure_logging(service_name="test", json_output=True)

        assert len(logger.handlers) == 1  # Only one handler


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger(self):
        """Test getting a logger."""
        logger = get_logger("my.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"

    def test_get_logger_same_instance(self):
        """Test that same name returns same logger."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")

        assert logger1 is logger2


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_log_context_basic(self):
        """Test basic log context usage."""
        with LogContext(order_id="123", symbol="AAPL"):
            # Context is active within the block
            pass
        # Context is cleared outside

    def test_log_context_as_context_manager(self):
        """Test log context returns self."""
        with LogContext(key="value") as ctx:
            assert isinstance(ctx, LogContext)
            assert ctx.extra == {"key": "value"}

    def test_log_context_nested(self):
        """Test nested log contexts."""
        with LogContext(outer="value"):
            with LogContext(inner="value"):
                pass
