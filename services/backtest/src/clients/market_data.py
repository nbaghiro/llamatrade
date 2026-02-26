"""Market data client for fetching historical bars."""

import os
from datetime import date, datetime

import httpx

from src.engine.backtester import BarData


class MarketDataError(Exception):
    """Error fetching market data."""

    pass


class MarketDataClient:
    """Client for fetching historical market data from the market-data service."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        """Initialize the market data client.

        Args:
            base_url: Base URL for the market-data service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("MARKET_DATA_URL", "http://localhost:47400")
        self.timeout = timeout

    async def fetch_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[BarData]]:
        """Fetch historical bars for multiple symbols.

        Args:
            symbols: List of symbols to fetch
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W)
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary mapping symbol to list of BarData
        """
        bars: dict[str, list[BarData]] = {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for symbol in symbols:
                try:
                    symbol_bars = await self._fetch_symbol_bars(
                        client, symbol, timeframe, start_date, end_date
                    )
                    bars[symbol] = symbol_bars
                except httpx.HTTPError as e:
                    raise MarketDataError(f"Failed to fetch bars for {symbol}: {e}") from e

        return bars

    async def _fetch_symbol_bars(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> list[BarData]:
        """Fetch bars for a single symbol."""
        response = await client.get(
            f"{self.base_url}/bars/{symbol}",
            params={
                "timeframe": timeframe,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
        )
        response.raise_for_status()

        data = response.json()
        raw_bars = data.get("bars", [])

        # Convert to BarData format
        bars: list[BarData] = []
        for bar in raw_bars:
            # Parse timestamp
            ts = bar.get("timestamp") or bar.get("t")
            if isinstance(ts, str):
                # Handle ISO format
                timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                timestamp = ts

            bars.append(
                {
                    "timestamp": timestamp,
                    "open": float(bar.get("open") or bar.get("o", 0)),
                    "high": float(bar.get("high") or bar.get("h", 0)),
                    "low": float(bar.get("low") or bar.get("l", 0)),
                    "close": float(bar.get("close") or bar.get("c", 0)),
                    "volume": int(bar.get("volume") or bar.get("v", 0)),
                }
            )

        return bars

    async def check_health(self) -> bool:
        """Check if market-data service is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return bool(response.status_code == 200)
        except httpx.HTTPError:
            return False
