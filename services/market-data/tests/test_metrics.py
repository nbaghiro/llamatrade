"""Tests for market data metrics module."""

from unittest.mock import MagicMock, patch

from src.metrics import (
    ALPACA_CIRCUIT_BREAKER_STATE,
    ALPACA_RATE_LIMIT_TOKENS,
    ALPACA_REQUEST_LATENCY,
    ALPACA_REQUESTS_TOTAL,
    CACHE_LATENCY,
    CACHE_OPERATIONS_TOTAL,
    STREAM_ALPACA_MESSAGES_TOTAL,
    STREAM_CONNECTIONS,
    STREAM_MESSAGES_TOTAL,
    STREAM_SUBSCRIPTIONS,
    record_alpaca_request,
    record_alpaca_stream_message,
    record_cache_operation,
    record_stream_message,
    update_circuit_breaker_metrics,
    update_rate_limiter_metrics,
    update_stream_metrics,
)


class TestRecordAlpacaRequest:
    """Tests for record_alpaca_request function."""

    def test_records_request_success(self):
        """Test recording a successful request."""
        # Get the labeled metric to verify it exists
        with patch.object(ALPACA_REQUESTS_TOTAL, "labels") as mock_labels:
            with patch.object(ALPACA_REQUEST_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_alpaca_request("get_bars", "success", 0.15)

                mock_labels.assert_called_once_with(method="get_bars", status="success")
                mock_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(method="get_bars")
                mock_histogram.observe.assert_called_once_with(0.15)

    def test_records_request_error(self):
        """Test recording a failed request."""
        with patch.object(ALPACA_REQUESTS_TOTAL, "labels") as mock_labels:
            with patch.object(ALPACA_REQUEST_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_alpaca_request("get_quote", "error", 0.5)

                mock_labels.assert_called_once_with(method="get_quote", status="error")
                mock_counter.inc.assert_called_once()

    def test_records_rate_limited(self):
        """Test recording a rate limited request."""
        with patch.object(ALPACA_REQUESTS_TOTAL, "labels") as mock_labels:
            with patch.object(ALPACA_REQUEST_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_alpaca_request("get_snapshot", "rate_limited", 0.01)

                mock_labels.assert_called_once_with(method="get_snapshot", status="rate_limited")


class TestRecordCacheOperation:
    """Tests for record_cache_operation function."""

    def test_records_cache_hit(self):
        """Test recording a cache hit."""
        with patch.object(CACHE_OPERATIONS_TOTAL, "labels") as mock_labels:
            with patch.object(CACHE_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_cache_operation("get", "hit", 0.001)

                mock_labels.assert_called_once_with(operation="get", result="hit")
                mock_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(operation="get")
                mock_histogram.observe.assert_called_once_with(0.001)

    def test_records_cache_miss(self):
        """Test recording a cache miss."""
        with patch.object(CACHE_OPERATIONS_TOTAL, "labels") as mock_labels:
            with patch.object(CACHE_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_cache_operation("get", "miss", 0.002)

                mock_labels.assert_called_once_with(operation="get", result="miss")

    def test_records_cache_set(self):
        """Test recording a cache set operation."""
        with patch.object(CACHE_OPERATIONS_TOTAL, "labels") as mock_labels:
            with patch.object(CACHE_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_cache_operation("set", "hit", 0.003)

                mock_labels.assert_called_once_with(operation="set", result="hit")

    def test_records_cache_error(self):
        """Test recording a cache error."""
        with patch.object(CACHE_OPERATIONS_TOTAL, "labels") as mock_labels:
            with patch.object(CACHE_LATENCY, "labels") as mock_latency_labels:
                mock_counter = MagicMock()
                mock_histogram = MagicMock()
                mock_labels.return_value = mock_counter
                mock_latency_labels.return_value = mock_histogram

                record_cache_operation("delete", "error", 0.01)

                mock_labels.assert_called_once_with(operation="delete", result="error")


class TestUpdateStreamMetrics:
    """Tests for update_stream_metrics function."""

    def test_updates_all_metrics(self):
        """Test updating all stream metrics."""
        with patch.object(STREAM_CONNECTIONS, "set") as mock_conn_set:
            with patch.object(STREAM_SUBSCRIPTIONS, "labels") as mock_sub_labels:
                mock_sub_gauge = MagicMock()
                mock_sub_labels.return_value = mock_sub_gauge

                update_stream_metrics(
                    connections=5,
                    trade_subs=10,
                    quote_subs=15,
                    bar_subs=8,
                )

                mock_conn_set.assert_called_once_with(5)
                assert mock_sub_labels.call_count == 3
                assert mock_sub_gauge.set.call_count == 3

    def test_updates_zero_values(self):
        """Test updating with zero values."""
        with patch.object(STREAM_CONNECTIONS, "set") as mock_conn_set:
            with patch.object(STREAM_SUBSCRIPTIONS, "labels") as mock_sub_labels:
                mock_sub_gauge = MagicMock()
                mock_sub_labels.return_value = mock_sub_gauge

                update_stream_metrics(
                    connections=0,
                    trade_subs=0,
                    quote_subs=0,
                    bar_subs=0,
                )

                mock_conn_set.assert_called_once_with(0)


class TestRecordStreamMessage:
    """Tests for record_stream_message function."""

    def test_records_trade_message(self):
        """Test recording a trade message."""
        with patch.object(STREAM_MESSAGES_TOTAL, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            record_stream_message("trade")

            mock_labels.assert_called_once_with(type="trade")
            mock_counter.inc.assert_called_once()

    def test_records_quote_message(self):
        """Test recording a quote message."""
        with patch.object(STREAM_MESSAGES_TOTAL, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            record_stream_message("quote")

            mock_labels.assert_called_once_with(type="quote")

    def test_records_bar_message(self):
        """Test recording a bar message."""
        with patch.object(STREAM_MESSAGES_TOTAL, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            record_stream_message("bar")

            mock_labels.assert_called_once_with(type="bar")


class TestRecordAlpacaStreamMessage:
    """Tests for record_alpaca_stream_message function."""

    def test_records_trade(self):
        """Test recording a trade from Alpaca stream."""
        with patch.object(STREAM_ALPACA_MESSAGES_TOTAL, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            record_alpaca_stream_message("trade")

            mock_labels.assert_called_once_with(type="trade")
            mock_counter.inc.assert_called_once()

    def test_records_error(self):
        """Test recording an error from Alpaca stream."""
        with patch.object(STREAM_ALPACA_MESSAGES_TOTAL, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            record_alpaca_stream_message("error")

            mock_labels.assert_called_once_with(type="error")


class TestUpdateRateLimiterMetrics:
    """Tests for update_rate_limiter_metrics function."""

    def test_updates_tokens(self):
        """Test updating rate limiter tokens."""
        with patch.object(ALPACA_RATE_LIMIT_TOKENS, "set") as mock_set:
            update_rate_limiter_metrics(100.5)

            mock_set.assert_called_once_with(100.5)

    def test_updates_zero_tokens(self):
        """Test updating with zero tokens."""
        with patch.object(ALPACA_RATE_LIMIT_TOKENS, "set") as mock_set:
            update_rate_limiter_metrics(0)

            mock_set.assert_called_once_with(0)


class TestUpdateCircuitBreakerMetrics:
    """Tests for update_circuit_breaker_metrics function."""

    def test_updates_closed_state(self):
        """Test updating circuit breaker to closed state."""
        with patch.object(ALPACA_CIRCUIT_BREAKER_STATE, "set") as mock_set:
            update_circuit_breaker_metrics("closed")

            mock_set.assert_called_once_with(0)

    def test_updates_half_open_state(self):
        """Test updating circuit breaker to half_open state."""
        with patch.object(ALPACA_CIRCUIT_BREAKER_STATE, "set") as mock_set:
            update_circuit_breaker_metrics("half_open")

            mock_set.assert_called_once_with(1)

    def test_updates_open_state(self):
        """Test updating circuit breaker to open state."""
        with patch.object(ALPACA_CIRCUIT_BREAKER_STATE, "set") as mock_set:
            update_circuit_breaker_metrics("open")

            mock_set.assert_called_once_with(2)

    def test_handles_unknown_state(self):
        """Test handling unknown circuit breaker state."""
        with patch.object(ALPACA_CIRCUIT_BREAKER_STATE, "set") as mock_set:
            update_circuit_breaker_metrics("unknown")

            mock_set.assert_called_once_with(-1)
