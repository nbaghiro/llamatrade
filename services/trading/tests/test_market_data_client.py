"""Trading's market-data wrapper: symbol normalization, degradation, bar mapping.

Drives the real ``src.clients.market_data.MarketDataClient`` with the underlying
proto client stubbed at its own seam, so the wrapper's own logic runs: upcasing,
the fail-soft paths that keep a market-data outage from breaking pricing, the
drop-unpriceable filter, and the bar dict projection.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.clients.market_data import MarketDataClient, get_market_data_client


def _client(**stub: object) -> tuple[MarketDataClient, AsyncMock]:
    """A wrapper whose underlying proto client is a stub with the given behavior."""
    client = MarketDataClient(target="market-data:8840")
    proto = AsyncMock()
    for name, value in stub.items():
        setattr(proto, name, value)
    client._client = proto
    return client, proto


class TestTargetResolution:
    def test_defaults_to_the_env_target(self) -> None:
        with patch.dict(os.environ, {"MARKET_DATA_GRPC_TARGET": "md:9999"}):
            assert MarketDataClient().target == "md:9999"

    def test_explicit_target_wins(self) -> None:
        assert MarketDataClient(target="other:1").target == "other:1"

    def test_client_is_created_once(self) -> None:
        client = MarketDataClient(target="md:1")
        assert client._client is None
        assert client._get_client() is client._get_client()

    async def test_close_releases_the_underlying_client(self) -> None:
        client, proto = _client()
        await client.close()
        proto.close.assert_awaited_once()
        assert client._client is None

    async def test_close_is_a_noop_without_a_client(self) -> None:
        await MarketDataClient(target="md:1").close()


class TestGetLatestPrice:
    async def test_upcases_the_symbol_and_returns_a_float(self) -> None:
        client, proto = _client(get_latest_price=AsyncMock(return_value=Decimal("101.25")))

        assert await client.get_latest_price("aapl") == 101.25
        proto.get_latest_price.assert_awaited_once_with("AAPL")

    async def test_upstream_failure_degrades_to_none(self) -> None:
        client, _ = _client(get_latest_price=AsyncMock(side_effect=RuntimeError("md down")))

        assert await client.get_latest_price("AAPL") is None


class TestGetPrices:
    async def test_empty_input_short_circuits_without_a_call(self) -> None:
        client, proto = _client(get_latest_prices=AsyncMock())

        assert await client.get_prices([]) == {}
        proto.get_latest_prices.assert_not_awaited()

    async def test_upcases_symbols_and_maps_to_floats(self) -> None:
        client, proto = _client(
            get_latest_prices=AsyncMock(return_value={"AAPL": Decimal("10"), "TLT": Decimal("20")})
        )

        assert await client.get_prices(["aapl", "tlt"]) == {"AAPL": 10.0, "TLT": 20.0}
        proto.get_latest_prices.assert_awaited_once_with(["AAPL", "TLT"])

    @pytest.mark.parametrize("unpriceable", [Decimal("0"), None])
    async def test_unpriceable_symbols_are_omitted_not_zeroed(self, unpriceable: object) -> None:
        """A caller must skip marking rather than mark a position to $0."""
        client, _ = _client(
            get_latest_prices=AsyncMock(return_value={"AAPL": Decimal("5"), "TLT": unpriceable})
        )

        assert await client.get_prices(["AAPL", "TLT"]) == {"AAPL": 5.0}

    async def test_upstream_failure_degrades_to_an_empty_map(self) -> None:
        client, _ = _client(get_latest_prices=AsyncMock(side_effect=RuntimeError("md down")))

        assert await client.get_prices(["AAPL"]) == {}


class TestGetSnapshot:
    async def test_upcases_and_passes_through(self) -> None:
        snapshot = SimpleNamespace(symbol="AAPL")
        client, proto = _client(get_snapshot=AsyncMock(return_value=snapshot))

        assert await client.get_snapshot("aapl") is snapshot
        proto.get_snapshot.assert_awaited_once_with("AAPL")

    async def test_upstream_failure_degrades_to_none(self) -> None:
        client, _ = _client(get_snapshot=AsyncMock(side_effect=RuntimeError("md down")))

        assert await client.get_snapshot("AAPL") is None


class TestGetBars:
    @staticmethod
    def _bar() -> SimpleNamespace:
        return SimpleNamespace(
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=100,
        )

    async def test_projects_bars_into_plain_dicts(self) -> None:
        client, proto = _client(get_historical_bars=AsyncMock(return_value=[self._bar()]))

        bars = await client.get_bars("aapl", timeframe="1D", limit=10)

        assert bars == [
            {
                "timestamp": "2026-01-02T00:00:00+00:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            }
        ]
        assert proto.get_historical_bars.await_args.kwargs["symbol"] == "AAPL"

    async def test_daily_window_pads_past_the_bar_count(self) -> None:
        """Daily bars count trading days, so the calendar window must be wider."""
        client, proto = _client(get_historical_bars=AsyncMock(return_value=[]))

        await client.get_bars("AAPL", timeframe="1D", limit=100)

        kwargs = proto.get_historical_bars.await_args.kwargs
        assert (kwargs["end"] - kwargs["start"]).days > 100

    async def test_intraday_window_tracks_the_requested_units(self) -> None:
        client, proto = _client(get_historical_bars=AsyncMock(return_value=[]))

        await client.get_bars("AAPL", timeframe="1Min", limit=30)

        kwargs = proto.get_historical_bars.await_args.kwargs
        assert (kwargs["end"] - kwargs["start"]).total_seconds() == pytest.approx(30 * 60, abs=5)

    async def test_upstream_failure_degrades_to_an_empty_list(self) -> None:
        client, _ = _client(get_historical_bars=AsyncMock(side_effect=RuntimeError("md down")))

        assert await client.get_bars("AAPL") == []


def test_module_singleton_is_reused() -> None:
    assert get_market_data_client() is get_market_data_client()
