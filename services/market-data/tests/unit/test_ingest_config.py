"""Unit tests for ingest config + backfill window planning (no DB)."""

from datetime import UTC, datetime, timedelta

from src.ingest.backfill import backfill_window
from src.ingest.config import IngestConfig, adjustment_for, get_universe


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


class TestAdjustmentFor:
    def test_daily_is_split_adjusted(self) -> None:
        assert adjustment_for("1Day") == "split"

    def test_intraday_is_raw(self) -> None:
        assert adjustment_for("1Min") == "raw"
        assert adjustment_for("1Hour") == "raw"

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
        monkeypatch.setenv("MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S", "5.5")
        cfg = IngestConfig.from_env()
        assert cfg.minute_lookback_days == 7
        assert cfg.max_concurrency == 8
        assert cfg.universe_refresh_interval_s == 5.5

    def test_universe_refresh_interval_defaults_to_a_minute(self, monkeypatch) -> None:
        monkeypatch.delenv("MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S", raising=False)
        assert IngestConfig.from_env().universe_refresh_interval_s == 60.0

    def test_from_env_reads_every_tunable(self, monkeypatch) -> None:
        env = {
            "MARKET_DATA_DAILY_LOOKBACK_DAYS": "30",
            "MARKET_DATA_MINUTE_LOOKBACK_DAYS": "7",
            "MARKET_DATA_INGEST_CONCURRENCY": "8",
            "MARKET_DATA_FETCH_LIMIT": "5000",
            "MARKET_DATA_BACKFILL_INTERVAL_S": "1800",
            "MARKET_DATA_GAP_REPAIR_INTERVAL_S": "600",
            "MARKET_DATA_CORPORATE_ACTION_INTERVAL_S": "43200",
            "MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S": "5.5",
            "MARKET_DATA_CORPORATE_ACTION_WINDOW_DAYS": "3",
        }
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        cfg = IngestConfig.from_env()
        assert cfg.daily_lookback_days == 30
        assert cfg.minute_lookback_days == 7
        assert cfg.max_concurrency == 8
        assert cfg.fetch_limit == 5000
        assert cfg.backfill_interval_s == 1800.0
        assert cfg.gap_repair_interval_s == 600.0
        assert cfg.corporate_action_interval_s == 43200.0
        assert cfg.universe_refresh_interval_s == 5.5
        assert cfg.corporate_action_window_days == 3

    def test_from_env_defaults_when_unset(self, monkeypatch) -> None:
        for name in (
            "MARKET_DATA_DAILY_LOOKBACK_DAYS",
            "MARKET_DATA_MINUTE_LOOKBACK_DAYS",
            "MARKET_DATA_INGEST_CONCURRENCY",
            "MARKET_DATA_FETCH_LIMIT",
            "MARKET_DATA_BACKFILL_INTERVAL_S",
            "MARKET_DATA_GAP_REPAIR_INTERVAL_S",
            "MARKET_DATA_CORPORATE_ACTION_INTERVAL_S",
            "MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S",
            "MARKET_DATA_CORPORATE_ACTION_WINDOW_DAYS",
        ):
            monkeypatch.delenv(name, raising=False)
        assert IngestConfig.from_env() == IngestConfig()
