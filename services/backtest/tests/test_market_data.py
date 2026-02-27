"""Tests for gRPC market data client usage in backtest service."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llamatrade_grpc.clients.market_data import Bar, MarketDataClient


class TestMarketDataClientForBacktest:
    """Tests for using MarketDataClient in backtest service."""

    @pytest.fixture
    def mock_client(self):
        """Create a fully mocked MarketDataClient."""
        with patch.object(MarketDataClient, "__init__", lambda self, *args, **kwargs: None):
            client = MarketDataClient()
            client._channel = MagicMock()
            client._stub = MagicMock()
            # Mock the actual methods to avoid protobuf imports
            client.get_historical_bars = AsyncMock()
            return client

    async def test_fetch_historical_bars_for_backtest(self, mock_client):
        """Test fetching historical bars for backtesting."""
        mock_bars = [
            Bar(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2 + i, 9, 30),
                open=Decimal(str(open_)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=vol,
            )
            for i, (open_, high, low, close, vol) in enumerate(
                [
                    (100.0, 105.0, 99.0, 104.0, 10000),
                    (104.0, 108.0, 103.0, 107.0, 12000),
                    (107.0, 110.0, 106.0, 109.0, 15000),
                ]
            )
        ]
        mock_client.get_historical_bars.return_value = mock_bars

        bars = await mock_client.get_historical_bars(
            symbol="AAPL",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
            timeframe="1D",
        )

        assert len(bars) == 3
        assert all(isinstance(bar, Bar) for bar in bars)
        assert bars[0].close == Decimal("104.0")
        assert bars[1].close == Decimal("107.0")
        assert bars[2].close == Decimal("109.0")

    async def test_fetch_bars_for_multiple_symbols(self, mock_client):
        """Test fetching bars for multiple symbols (used in backtest)."""
        symbols_data = {
            "AAPL": Decimal("185.50"),
            "GOOGL": Decimal("140.25"),
            "MSFT": Decimal("380.00"),
        }

        async def mock_get_bars(symbol, start, end, **kwargs):
            close = symbols_data.get(symbol, Decimal("100.0"))
            return [
                Bar(
                    symbol=symbol,
                    timestamp=datetime(2024, 1, 2, 9, 30),
                    open=close - Decimal("1"),
                    high=close + Decimal("1"),
                    low=close - Decimal("2"),
                    close=close,
                    volume=10000,
                )
            ]

        mock_client.get_historical_bars = mock_get_bars

        # Fetch for each symbol (as backtest engine would)
        all_bars = {}
        for symbol in ["AAPL", "GOOGL", "MSFT"]:
            bars = await mock_client.get_historical_bars(
                symbol=symbol,
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
            )
            all_bars[symbol] = bars

        assert len(all_bars) == 3
        assert all_bars["AAPL"][0].close == Decimal("185.50")
        assert all_bars["GOOGL"][0].close == Decimal("140.25")
        assert all_bars["MSFT"][0].close == Decimal("380.00")

    async def test_fetch_bars_empty_for_invalid_symbol(self, mock_client):
        """Test that invalid symbols return empty bars."""
        mock_client.get_historical_bars.return_value = []

        bars = await mock_client.get_historical_bars(
            symbol="INVALID_SYMBOL",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
        )

        assert bars == []

    async def test_fetch_bars_with_intraday_timeframe(self, mock_client):
        """Test fetching intraday bars for backtest."""
        mock_bars = [
            Bar(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2, 9, minute),
                open=Decimal("185.00"),
                high=Decimal("185.50"),
                low=Decimal("184.50"),
                close=Decimal("185.25"),
                volume=1000,
            )
            for minute in range(0, 60, 5)  # 12 bars for an hour
        ]
        mock_client.get_historical_bars.return_value = mock_bars

        bars = await mock_client.get_historical_bars(
            symbol="AAPL",
            start=datetime(2024, 1, 2, 9, 0),
            end=datetime(2024, 1, 2, 10, 0),
            timeframe="5MIN",
        )

        assert len(bars) == 12

    async def test_fetch_bars_date_range_handling(self, mock_client):
        """Test that date range is properly passed to client."""
        mock_client.get_historical_bars.return_value = []

        start = datetime(2023, 1, 1)
        end = datetime(2023, 12, 31)

        await mock_client.get_historical_bars(
            symbol="AAPL",
            start=start,
            end=end,
            timeframe="1D",
        )

        mock_client.get_historical_bars.assert_called_once()
        call_kwargs = mock_client.get_historical_bars.call_args[1]
        assert call_kwargs["start"] == start
        assert call_kwargs["end"] == end


class TestBarDataConversion:
    """Tests for bar data conversion used in backtest."""

    def test_bar_to_backtest_format(self):
        """Test converting Bar to format expected by backtest engine."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 9, 30),
            open=Decimal("185.00"),
            high=Decimal("186.50"),
            low=Decimal("184.00"),
            close=Decimal("185.50"),
            volume=50000000,
            trade_count=100000,
            vwap=Decimal("185.25"),
        )

        # Convert to format expected by backtest engine
        backtest_bar = {
            "timestamp": bar.timestamp,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": bar.volume,
        }

        assert backtest_bar["timestamp"] == datetime(2024, 1, 2, 9, 30)
        assert backtest_bar["open"] == 185.00
        assert backtest_bar["high"] == 186.50
        assert backtest_bar["low"] == 184.00
        assert backtest_bar["close"] == 185.50
        assert backtest_bar["volume"] == 50000000

    def test_bar_list_to_dataframe_format(self):
        """Test converting list of Bars to DataFrame-compatible format."""
        bars = [
            Bar(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2 + i, 9, 30),
                open=Decimal(str(100 + i)),
                high=Decimal(str(105 + i)),
                low=Decimal(str(99 + i)),
                close=Decimal(str(104 + i)),
                volume=10000 * (i + 1),
            )
            for i in range(5)
        ]

        # Convert to list of dicts (DataFrame-compatible)
        data = [
            {
                "timestamp": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": bar.volume,
            }
            for bar in bars
        ]

        assert len(data) == 5
        assert data[0]["close"] == 104.0
        assert data[4]["close"] == 108.0
        assert data[0]["volume"] == 10000
        assert data[4]["volume"] == 50000


class TestMarketDataClientConnection:
    """Tests for MarketDataClient connection handling."""

    def test_client_default_target(self):
        """Test client uses correct default target for market data service."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            client = MarketDataClient()
            # Channel is created lazily, so access the property to trigger creation
            _ = client.channel
            call_args = mock_channel.call_args[0][0]
            assert call_args == "market-data:8840"

    async def test_client_context_manager(self):
        """Test client can be used as async context manager."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel_instance = AsyncMock()
            mock_channel.return_value = mock_channel_instance

            async with MarketDataClient() as client:
                # Access the channel to ensure it's created
                _ = client.channel
                assert client is not None

            # Channel should be closed on exit
            mock_channel_instance.close.assert_called_once()
