"""Clients for external services.

All inter-service communication uses gRPC via llamatrade_grpc.

Usage:
    from llamatrade_grpc.clients import MarketDataClient

    async with MarketDataClient() as client:
        bars = await client.get_historical_bars(...)
"""

__all__: list[str] = []
