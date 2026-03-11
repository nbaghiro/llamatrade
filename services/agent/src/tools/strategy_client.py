"""Strategy service client for creating strategies from artifacts."""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# Strategy service URL
STRATEGY_SERVICE_URL = os.getenv("STRATEGY_SERVICE_URL", "http://localhost:8820")


class StrategyClient:
    """Client for communicating with the Strategy service.

    This client uses the Connect protocol (JSON over HTTP) to communicate
    with the strategy service's gRPC endpoints.
    """

    def __init__(self) -> None:
        """Initialize the strategy client."""
        self.base_url = STRATEGY_SERVICE_URL
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def create_strategy(
        self,
        tenant_id: UUID,
        user_id: UUID,
        name: str,
        dsl_code: str,
        description: str | None = None,
        symbols: list[str] | None = None,
        timeframe: str = "1D",
    ) -> dict[str, Any] | None:
        """Create a new strategy via the Strategy service.

        Uses Connect protocol to call the StrategyService.CreateStrategy RPC.

        Args:
            tenant_id: Tenant UUID
            user_id: User UUID (for ownership/audit)
            name: Strategy name
            dsl_code: Strategy DSL code
            description: Optional description
            symbols: Extracted symbols
            timeframe: Strategy timeframe

        Returns:
            Created strategy data dict, or None on failure
        """
        client = await self._get_client()

        try:
            # Build the Connect RPC request payload
            # Uses snake_case field names to match proto definitions
            payload = {
                "context": {
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id),
                },
                "name": name,
                "description": description or "",
                "dsl_code": dsl_code,
            }

            # Connect protocol URL: /{package}.{Service}/{Method}
            url = "/llamatrade.StrategyService/CreateStrategy"

            # Make Connect RPC request
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 200:
                data = response.json()
                # Connect response wraps the strategy in a "strategy" field
                strategy = data.get("strategy", data)
                logger.info(
                    "Created strategy %s via StrategyService",
                    strategy.get("id"),
                )
                return strategy

            logger.error(
                "Failed to create strategy: %s %s",
                response.status_code,
                response.text,
            )
            return None

        except httpx.HTTPError as e:
            logger.exception("HTTP error creating strategy: %s", e)
            return None
        except Exception as e:
            logger.exception("Error creating strategy: %s", e)
            return None


# Global client instance
_client: StrategyClient | None = None


def get_strategy_client() -> StrategyClient:
    """Get or create the global strategy client."""
    global _client
    if _client is None:
        _client = StrategyClient()
    return _client
