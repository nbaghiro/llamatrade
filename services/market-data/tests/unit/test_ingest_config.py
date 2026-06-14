"""Unit tests for ingest config + backfill window planning (no DB)."""

from datetime import UTC, datetime, timedelta

from src.ingest.backfill import backfill_window
from src.ingest.config import IngestConfig, get_universe


class TestBackfillWindow:
    def test_window_is_lookback_before_now(self) -> None:
        now = datetime(2026, 6, 1, tzinfo=UTC)
        start, end = backfill_window(now, lookback_days=10)
        assert end == now
        assert start == now - timedelta(days=10)


class TestGetUniverse:
    def test_parses_uppercases_and_dedupes(self, monkeypatch) -> None:
        monkeypatch.setenv("MARKET_DATA_UNIVERSE", "aapl, MSFT ,aapl,, tsla")
        assert get_universe() == ["AAPL", "MSFT", "TSLA"]

    def test_empty_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("MARKET_DATA_UNIVERSE", raising=False)
        assert get_universe() == []


class TestIngestConfig:
    def test_defaults(self) -> None:
        cfg = IngestConfig()
        assert cfg.lookback_days("1Day") == cfg.daily_lookback_days
        assert cfg.lookback_days("1Min") == cfg.minute_lookback_days

    def test_from_env_overrides(self, monkeypatch) -> None:
        monkeypatch.setenv("MARKET_DATA_MINUTE_LOOKBACK_DAYS", "7")
        monkeypatch.setenv("MARKET_DATA_INGEST_CONCURRENCY", "8")
        cfg = IngestConfig.from_env()
        assert cfg.minute_lookback_days == 7
        assert cfg.max_concurrency == 8
