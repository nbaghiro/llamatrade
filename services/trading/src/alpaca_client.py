"""Alpaca Trading API client."""

import os
from typing import TypedDict
from uuid import UUID

import httpx

from src.metrics import time_alpaca_call
from src.models import PositionResponse


class AlpacaAccountResponse(TypedDict):
    """Alpaca account API response."""

    id: str
    account_number: str
    status: str
    cash: str
    portfolio_value: str
    buying_power: str
    equity: str
    currency: str


class AlpacaOrderResponse(TypedDict, total=False):
    """Alpaca order API response."""

    id: str
    client_order_id: str
    symbol: str
    qty: str
    side: str
    type: str
    status: str
    filled_qty: str
    filled_avg_price: str | None
    created_at: str
    submitted_at: str
    filled_at: str | None


class AlpacaTradingClient:
    """Client for Alpaca Trading API."""

    LIVE_URL = "https://api.alpaca.markets/v2"
    PAPER_URL = "https://paper-api.alpaca.markets/v2"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
    ):
        env_api_key = os.getenv("ALPACA_API_KEY")
        env_api_secret = os.getenv("ALPACA_API_SECRET")
        self.api_key: str = api_key or env_api_key or ""
        self.api_secret: str = api_secret or env_api_secret or ""
        self.paper = paper
        self.base_url = self.PAPER_URL if paper else self.LIVE_URL

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.api_secret,
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def get_account(self) -> AlpacaAccountResponse:
        """Get account information."""
        async with time_alpaca_call("get_account"):
            response = await self._client.get("/account")
            response.raise_for_status()
            result: AlpacaAccountResponse = response.json()
            return result

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str,
        time_in_force: str = "day",
        limit_price: float | None = None,
        stop_price: float | None = None,
        client_order_id: str | None = None,
    ) -> AlpacaOrderResponse:
        """Submit an order.

        Args:
            symbol: Stock symbol.
            qty: Number of shares.
            side: "buy" or "sell".
            order_type: "market", "limit", "stop", "stop_limit".
            time_in_force: Order duration ("day", "gtc", etc.).
            limit_price: Limit price for limit orders.
            stop_price: Stop price for stop orders.
            client_order_id: Idempotency key. If provided, Alpaca will return
                existing order if one with this ID already exists.

        Returns:
            Alpaca order response.
        """
        data: dict[str, str] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price:
            data["limit_price"] = str(limit_price)
        if stop_price:
            data["stop_price"] = str(stop_price)
        if client_order_id:
            data["client_order_id"] = client_order_id

        async with time_alpaca_call("submit_order"):
            response = await self._client.post("/orders", json=data)
            response.raise_for_status()
            result: AlpacaOrderResponse = response.json()
            return result

    async def get_order(self, order_id: str) -> AlpacaOrderResponse | None:
        """Get order by Alpaca order ID."""
        async with time_alpaca_call("get_order"):
            try:
                response = await self._client.get(f"/orders/{order_id}")
                response.raise_for_status()
                result: AlpacaOrderResponse = response.json()
                return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise

    async def get_order_by_client_id(self, client_order_id: str) -> AlpacaOrderResponse | None:
        """Get order by client order ID.

        Useful for crash recovery - check if an order was actually
        submitted even if we crashed before recording the response.

        Args:
            client_order_id: The client-provided idempotency key.

        Returns:
            Order if found, None otherwise.
        """
        async with time_alpaca_call("get_order_by_client_id"):
            try:
                response = await self._client.get(
                    "/orders:by_client_order_id",
                    params={"client_order_id": client_order_id},
                )
                response.raise_for_status()
                result: AlpacaOrderResponse = response.json()
                return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        async with time_alpaca_call("cancel_order"):
            try:
                response = await self._client.delete(f"/orders/{order_id}")
                return bool(response.status_code == 204)
            except httpx.HTTPStatusError:
                return False

    async def get_positions(self, tenant_id: UUID) -> list[PositionResponse]:
        """Get all open positions."""
        async with time_alpaca_call("get_positions"):
            response = await self._client.get("/positions")
            response.raise_for_status()
            data = response.json()

            return [
                PositionResponse(
                    symbol=p["symbol"],
                    qty=float(p["qty"]),
                    side=p["side"],
                    cost_basis=float(p["cost_basis"]),
                    market_value=float(p["market_value"]),
                    unrealized_pnl=float(p["unrealized_pl"]),
                    unrealized_pnl_percent=float(p["unrealized_plpc"]) * 100,
                    current_price=float(p["current_price"]),
                )
                for p in data
            ]

    async def get_position(self, tenant_id: UUID, symbol: str) -> PositionResponse | None:
        """Get position for a symbol."""
        async with time_alpaca_call("get_position"):
            try:
                response = await self._client.get(f"/positions/{symbol}")
                response.raise_for_status()
                p = response.json()
                return PositionResponse(
                    symbol=p["symbol"],
                    qty=float(p["qty"]),
                    side=p["side"],
                    cost_basis=float(p["cost_basis"]),
                    market_value=float(p["market_value"]),
                    unrealized_pnl=float(p["unrealized_pl"]),
                    unrealized_pnl_percent=float(p["unrealized_plpc"]) * 100,
                    current_price=float(p["current_price"]),
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise

    async def close_position(self, tenant_id: UUID, symbol: str) -> bool:
        """Close a position."""
        async with time_alpaca_call("close_position"):
            try:
                response = await self._client.delete(f"/positions/{symbol}")
                return response.status_code in (200, 204)
            except httpx.HTTPStatusError:
                return False

    async def close_all_positions(self, tenant_id: UUID) -> bool:
        """Close all positions."""
        async with time_alpaca_call("close_all_positions"):
            try:
                response = await self._client.delete("/positions")
                return response.status_code in (200, 204, 207)
            except httpx.HTTPStatusError:
                return False


_client: AlpacaTradingClient | None = None


def get_alpaca_trading_client() -> AlpacaTradingClient:
    """Dependency to get Alpaca trading client."""
    global _client
    if _client is None:
        _client = AlpacaTradingClient()
    return _client
