"""Clients for external services.

All inter-service communication uses Connect protocol via llamatrade_proto.

Usage:
    from llamatrade_proto.clients import MarketDataClient

    async with MarketDataClient() as client:
        bars = await client.get_historical_bars(...)
"""

__all__: list[str] = []
