"""Alpaca Trading API client.

Provides a ready-to-use client for trading operations including order submission,
position management, and account information.

Example:
    from llamatrade_alpaca import TradingClient

    client = TradingClient(paper=True)
    order = await client.submit_order("AAPL", qty=10, side="buy", type="market")
    positions = await client.get_positions()
"""

import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal, cast

from ..client_base import AlpacaClientBase
from ..config import AlpacaCredentials, AlpacaUrls
from ..errors import InvalidRequestError, OrderNotFoundError, PositionNotFoundError
from ..metrics import time_alpaca_call
from ..models import (
    Account,
    Asset,
    CorporateActionDateType,
    CorporateActionType,
    CorporateAnnouncement,
    MarketClock,
    Order,
    OrderSide,
    OrderType,
    Position,
    TimeInForce,
    parse_account,
    parse_asset,
    parse_clock,
    parse_corporate_announcement,
    parse_order,
    parse_position,
)
from ..resilience import RetryConfig, create_trading_resilience, retry_with_backoff

logger = logging.getLogger(__name__)

# Alpaca rejects an announcements window wider than 90 days.
MAX_ANNOUNCEMENT_WINDOW_DAYS = 90
ALL_CORPORATE_ACTION_TYPES: tuple[CorporateActionType, ...] = tuple(CorporateActionType)


class TradingClient(AlpacaClientBase):
    """Client for Alpaca Trading API.

    Provides methods for:
    - Account information
    - Order submission and management
    - Position management
    - Market clock

    All methods raise exceptions on errors (no OperationResult pattern).
    """

    BASE_URL_LIVE = AlpacaUrls.TRADING_LIVE
    BASE_URL_PAPER = AlpacaUrls.TRADING_PAPER

    def __init__(
        self,
        credentials: AlpacaCredentials | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
        timeout: float = 30.0,
    ):
        """Initialize Alpaca Trading Client.

        Args:
            credentials: Pre-configured credentials (takes precedence)
            api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
            api_secret: Alpaca API secret (defaults to ALPACA_API_SECRET env var)
            paper: Use paper trading environment (default True)
            timeout: HTTP request timeout in seconds
        """
        rate_limiter, circuit_breaker = create_trading_resilience()
        super().__init__(
            credentials=credentials,
            api_key=api_key,
            api_secret=api_secret,
            paper=paper,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            timeout=timeout,
        )

    # Account

    @retry_with_backoff(RetryConfig())
    async def get_account(self) -> Account:
        """Get account information.

        Returns:
            Account with cash, equity, buying power, etc.

        Raises:
            AuthenticationError: If credentials are invalid
            AlpacaError: On other API errors
        """
        async with time_alpaca_call("get_account"):
            response = await self._get("/account")
            return parse_account(response.json())

    # Orders

    @retry_with_backoff(RetryConfig())
    async def submit_order(
        self,
        symbol: str,
        qty: Decimal,
        side: OrderSide | Literal["buy", "sell"],
        order_type: OrderType | Literal["market", "limit", "stop", "stop_limit"] = "market",
        time_in_force: TimeInForce | Literal["day", "gtc", "ioc", "fok"] = "day",
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        client_order_id: str | None = None,
        extended_hours: bool = False,
    ) -> Order:
        """Submit an order.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            qty: Number of shares
            side: "buy" or "sell"
            order_type: Order type ("market", "limit", "stop", "stop_limit")
            time_in_force: Duration ("day", "gtc", "ioc", "fok")
            limit_price: Limit price for limit orders
            stop_price: Stop price for stop orders
            client_order_id: Idempotency key
            extended_hours: Allow extended hours trading

        Returns:
            Submitted Order

        Raises:
            InvalidRequestError: If order parameters are invalid
            AlpacaError: On API errors
        """
        # Convert enums to strings for API
        side_str = side.value if isinstance(side, OrderSide) else side
        type_str = order_type.value if isinstance(order_type, OrderType) else order_type
        tif_str = time_in_force.value if isinstance(time_in_force, TimeInForce) else time_in_force

        data: dict[str, str | bool] = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side_str,
            "type": type_str,
            "time_in_force": tif_str,
        }
        if limit_price is not None:
            data["limit_price"] = str(limit_price)
        if stop_price is not None:
            data["stop_price"] = str(stop_price)
        if client_order_id:
            data["client_order_id"] = client_order_id
        if extended_hours:
            data["extended_hours"] = True

        async with time_alpaca_call("submit_order"):
            response = await self._post("/orders", json=data)
            return parse_order(response.json())

    @retry_with_backoff(RetryConfig())
    async def get_order(self, order_id: str) -> Order | None:
        """Get order by Alpaca order ID.

        Args:
            order_id: Alpaca order ID

        Returns:
            Order if found, None otherwise

        Raises:
            AlpacaError: On API errors (except 404)
        """
        async with time_alpaca_call("get_order"):
            try:
                response = await self._get(f"/orders/{order_id}")
                return parse_order(response.json())
            except Exception as e:
                if getattr(e, "status_code", None) == 404:
                    return None
                raise

    @retry_with_backoff(RetryConfig())
    async def get_order_by_client_id(self, client_order_id: str) -> Order | None:
        """Get order by client order ID.

        Useful for crash recovery - check if an order was submitted
        even if we crashed before recording the response.

        Args:
            client_order_id: Client-provided idempotency key

        Returns:
            Order if found, None otherwise

        Raises:
            AlpacaError: On API errors (except 404)
        """
        async with time_alpaca_call("get_order_by_client_id"):
            try:
                response = await self._get(
                    "/orders:by_client_order_id",
                    params={"client_order_id": client_order_id},
                )
                return parse_order(response.json())
            except Exception as e:
                if getattr(e, "status_code", None) == 404:
                    return None
                raise

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order.

        Args:
            order_id: Alpaca order ID to cancel

        Raises:
            OrderNotFoundError: If order doesn't exist
            AlpacaError: On other API errors
        """
        async with time_alpaca_call("cancel_order"):
            try:
                response = await self._delete(f"/orders/{order_id}")
                if response.status_code == 204:
                    logger.info(f"Cancelled order {order_id}")
                    return
                # Unexpected but successful status code
                logger.debug(f"Cancel order returned status {response.status_code}")
            except Exception as e:
                if getattr(e, "status_code", None) == 404:
                    raise OrderNotFoundError(order_id) from e
                raise

    async def cancel_all_orders(self) -> list[Order]:
        """Cancel all open orders.

        Returns:
            List of cancelled orders

        Raises:
            AlpacaError: On API errors
        """
        async with time_alpaca_call("cancel_all_orders"):
            response = await self._delete("/orders")
            # Response is a list of cancelled orders
            raw_data: list[dict[str, Any]] = response.json()
            results: list[Order] = []
            for item in raw_data:
                body = item.get("body")
                order_data = cast(dict[str, Any], body) if isinstance(body, dict) else item
                results.append(parse_order(order_data))
            return results

    # Positions

    @retry_with_backoff(RetryConfig())
    async def get_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of Position objects

        Raises:
            AlpacaError: On API errors
        """
        async with time_alpaca_call("get_positions"):
            response = await self._get("/positions")
            data = response.json()
            return [parse_position(p) for p in data]

    @retry_with_backoff(RetryConfig())
    async def get_position(self, symbol: str) -> Position | None:
        """Get position for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Position if exists, None otherwise

        Raises:
            AlpacaError: On API errors (except 404)
        """
        async with time_alpaca_call("get_position"):
            try:
                response = await self._get(f"/positions/{symbol.upper()}")
                return parse_position(response.json())
            except Exception as e:
                if getattr(e, "status_code", None) == 404:
                    return None
                raise

    async def get_asset(self, symbol: str) -> Asset | None:
        """Get an asset's metadata (incl. tradability), or None if unknown.

        Args:
            symbol: Stock symbol

        Returns:
            Asset if it exists on Alpaca, None on 404 (unknown symbol).

        Raises:
            AlpacaError: On API errors (except 404)
        """
        async with time_alpaca_call("get_asset"):
            try:
                response = await self._get(f"/assets/{symbol.upper()}")
                return parse_asset(response.json())
            except Exception as e:
                if getattr(e, "status_code", None) == 404:
                    return None
                raise

    async def list_assets(
        self,
        *,
        status: str = "active",
        asset_class: str = "us_equity",
    ) -> list[Asset]:
        """List tradable assets from Alpaca's ``/v2/assets`` endpoint.

        Args:
            status: 'active' or 'inactive' (default 'active').
            asset_class: e.g. 'us_equity' (default).

        Returns:
            Asset metadata for every matching asset (``/v2/assets`` returns the full list).

        Raises:
            AlpacaError: On API errors.
        """
        async with time_alpaca_call("list_assets"):
            response = await self._get(
                "/assets", params={"status": status, "asset_class": asset_class}
            )
            return [parse_asset(item) for item in response.json()]

    async def close_position(self, symbol: str, qty: Decimal | None = None) -> Order:
        """Close a position (fully or partially).

        Args:
            symbol: Stock symbol
            qty: Number of shares to close (None = close all)

        Returns:
            Liquidation order

        Raises:
            PositionNotFoundError: If position doesn't exist
            AlpacaError: On other API errors
        """
        async with time_alpaca_call("close_position"):
            try:
                params: dict[str, str] = {}
                if qty is not None:
                    params["qty"] = str(qty)

                response = await self._delete(f"/positions/{symbol.upper()}", params=params or None)
                logger.info(f"Closed position for {symbol}")
                return parse_order(response.json())
            except Exception as e:
                if getattr(e, "status_code", None) == 404:
                    raise PositionNotFoundError(symbol) from e
                raise

    async def close_all_positions(self, cancel_orders: bool = True) -> list[Order]:
        """Close all positions.

        Args:
            cancel_orders: Also cancel all open orders (default True)

        Returns:
            List of liquidation orders

        Raises:
            AlpacaError: On API errors
        """
        async with time_alpaca_call("close_all_positions"):
            params = {"cancel_orders": str(cancel_orders).lower()}
            response = await self._delete("/positions", params=params)

            data: list[dict[str, Any]] = response.json()
            logger.info(f"Closed all positions: {len(data)} liquidation orders")

            # Response is list of orders or order wrappers
            orders: list[Order] = []
            for item in data:
                # Handle wrapped response format
                body = item.get("body")
                order_data = cast(dict[str, Any], body) if isinstance(body, dict) else item
                orders.append(parse_order(order_data))
            return orders

    # Corporate actions

    @retry_with_backoff(RetryConfig())
    async def get_corporate_announcements(
        self,
        *,
        since: date,
        until: date,
        ca_types: Sequence[CorporateActionType | str] = ALL_CORPORATE_ACTION_TYPES,
        symbol: str | None = None,
        cusip: str | None = None,
        date_type: CorporateActionDateType | str | None = None,
    ) -> list[CorporateAnnouncement]:
        """Get announced corporate actions (dividends, splits, mergers, spinoffs).

        Args:
            since: Start of the announcement window (inclusive)
            until: End of the announcement window (inclusive, <= 90 days after since)
            ca_types: Action categories to include (defaults to all four)
            symbol: Restrict to announcements initiated by this symbol
            cusip: Restrict to announcements initiated by this CUSIP
            date_type: Which announcement date the window filters on
                (declaration/ex/record/payable; Alpaca's default when omitted)

        Returns:
            Announcements matching the filter (empty list when none)

        Raises:
            InvalidRequestError: If the window is inverted or wider than 90 days
            AlpacaError: On API errors
        """
        if until < since:
            raise InvalidRequestError(f"until {until} precedes since {since}")
        if (until - since).days > MAX_ANNOUNCEMENT_WINDOW_DAYS:
            raise InvalidRequestError(
                f"announcement window {since}..{until} exceeds {MAX_ANNOUNCEMENT_WINDOW_DAYS} days"
            )
        if not ca_types:
            raise InvalidRequestError("ca_types must name at least one corporate-action type")

        params: dict[str, str] = {
            "ca_types": ",".join(str(t) for t in ca_types),
            "since": since.isoformat(),
            "until": until.isoformat(),
        }
        if symbol:
            params["symbol"] = symbol.upper()
        if cusip:
            params["cusip"] = cusip
        if date_type:
            params["date_type"] = str(date_type)

        async with time_alpaca_call("get_corporate_announcements"):
            response = await self._get("/corporate_actions/announcements", params=params)
            return [parse_corporate_announcement(item) for item in response.json()]

    # Market Clock

    @retry_with_backoff(RetryConfig())
    async def get_clock(self) -> MarketClock:
        """Get current market clock.

        Returns:
            MarketClock with is_open, next_open, next_close

        Raises:
            AlpacaError: On API errors
        """
        async with time_alpaca_call("get_clock"):
            response = await self._get("/clock")
            return parse_clock(response.json())
