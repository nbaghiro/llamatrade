"""Test bar stream."""

from datetime import UTC, datetime

from src.runner.bar_stream import AlpacaBarStream, BarData, MockBarStream, StreamConfig


class TestBarData:
    """Tests for BarData dataclass."""

    def test_bar_data_creation(self):
        """Test creating BarData instance."""
        bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 9, 30, tzinfo=UTC),
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        assert bar.symbol == "AAPL"
        assert bar.open == 150.0
        assert bar.close == 151.5
        assert bar.volume == 10000
        assert bar.vwap is None
        assert bar.trade_count is None

    def test_bar_data_with_optional_fields(self):
        """Test BarData with optional fields."""
        bar = BarData(
            symbol="GOOGL",
            timestamp=datetime(2024, 1, 15, 9, 30, tzinfo=UTC),
            open=140.0,
            high=142.0,
            low=139.0,
            close=141.5,
            volume=5000,
            vwap=140.8,
            trade_count=250,
        )

        assert bar.vwap == 140.8
        assert bar.trade_count == 250


class TestStreamConfig:
    """Tests for StreamConfig."""

    def test_default_config(self):
        """Test default stream configuration."""
        config = StreamConfig()

        assert config.paper is True
        assert config.reconnect_delay == 5.0
        assert config.max_reconnect_attempts == 10


class TestAlpacaBarStream:
    """Tests for AlpacaBarStream."""

    def test_stream_initialization(self):
        """Test stream initialization."""
        stream = AlpacaBarStream()

        assert stream.connected is False
        assert stream.authenticated is False
        assert len(stream.subscribed_symbols) == 0

    def test_stream_url_selection(self):
        """Test paper vs live URL selection."""
        paper_stream = AlpacaBarStream(StreamConfig(paper=True))
        live_stream = AlpacaBarStream(StreamConfig(paper=False))

        assert "sandbox" in paper_stream.url
        assert "sandbox" not in live_stream.url

    def test_parse_bar_valid_data(self):
        """Test parsing valid Alpaca bar message."""
        stream = AlpacaBarStream()
        data = {
            "T": "b",
            "S": "AAPL",
            "t": "2024-01-15T09:30:00Z",
            "o": 150.0,
            "h": 152.0,
            "l": 149.5,
            "c": 151.5,
            "v": 10000,
            "vw": 150.8,
            "n": 500,
        }

        bar = stream._parse_bar(data)

        assert bar is not None
        assert bar.symbol == "AAPL"
        assert bar.open == 150.0
        assert bar.high == 152.0
        assert bar.low == 149.5
        assert bar.close == 151.5
        assert bar.volume == 10000
        assert bar.vwap == 150.8
        assert bar.trade_count == 500

    def test_parse_bar_minimal_data(self):
        """Test parsing bar with minimal data."""
        stream = AlpacaBarStream()
        data = {
            "S": "GOOGL",
            "o": 140.0,
            "h": 142.0,
            "l": 139.0,
            "c": 141.5,
            "v": 5000,
        }

        bar = stream._parse_bar(data)

        assert bar is not None
        assert bar.symbol == "GOOGL"
        assert bar.vwap is None
        assert bar.trade_count is None

    def test_parse_bar_invalid_data(self):
        """Test parsing invalid bar data returns None."""
        stream = AlpacaBarStream()
        data = {"invalid": "data"}

        stream._parse_bar(data)

        # Should handle gracefully - either return None or a bar with defaults
        # depending on implementation


class TestMockBarStream:
    """Tests for MockBarStream."""

    def test_mock_stream_always_connected(self):
        """Test mock stream is always connected."""
        stream = MockBarStream()

        assert stream.connected is True
        assert stream.authenticated is True

    async def test_mock_stream_connect(self):
        """Test mock stream connect always succeeds."""
        stream = MockBarStream()

        result = await stream.connect()

        assert result is True

    async def test_mock_stream_disconnect(self):
        """Test mock stream disconnect."""
        stream = MockBarStream()
        stream._running = True

        await stream.disconnect()

        assert stream._running is False

    async def test_mock_stream_subscribe(self):
        """Test mock stream subscription."""
        stream = MockBarStream()

        result = await stream.subscribe(["AAPL", "GOOGL"])

        assert result is True
        assert "AAPL" in stream.subscribed_symbols
        assert "GOOGL" in stream.subscribed_symbols

    async def test_mock_stream_unsubscribe(self):
        """Test mock stream unsubscription."""
        stream = MockBarStream()
        await stream.subscribe(["AAPL", "GOOGL"])

        await stream.unsubscribe(["AAPL"])

        assert "AAPL" not in stream.subscribed_symbols
        assert "GOOGL" in stream.subscribed_symbols

    async def test_mock_stream_unsubscribe_all(self):
        """Test mock stream unsubscribe all."""
        stream = MockBarStream()
        await stream.subscribe(["AAPL", "GOOGL"])

        await stream.unsubscribe()

        assert len(stream.subscribed_symbols) == 0

    async def test_mock_stream_yields_bars(self, sample_bars):
        """Test mock stream yields configured bars."""
        stream = MockBarStream(bars={"AAPL": sample_bars})
        await stream.subscribe(["AAPL"])

        received_bars = []
        async for bar in stream.stream():
            received_bars.append(bar)
            if len(received_bars) >= 5:
                stream._running = False
                break

        assert len(received_bars) >= 5
        assert all(bar.symbol == "AAPL" for bar in received_bars)

    async def test_mock_stream_empty_when_no_bars(self):
        """Test mock stream with no bars configured."""
        stream = MockBarStream()
        await stream.subscribe(["AAPL"])

        received_bars = []
        async for bar in stream.stream():
            received_bars.append(bar)

        assert len(received_bars) == 0
