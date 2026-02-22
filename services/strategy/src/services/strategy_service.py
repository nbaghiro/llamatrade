"""Strategy service - strategy CRUD operations."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.models import StrategyConfig, StrategyStatus, StrategyType


class StrategyService:
    """Service for strategy management operations."""

    def __init__(self):
        # In production, inject database session
        pass

    async def create_strategy(
        self,
        tenant_id: UUID,
        name: str,
        description: str | None,
        strategy_type: StrategyType,
        config: StrategyConfig,
    ) -> dict[str, Any]:
        """Create a new strategy."""
        strategy_id = uuid4()
        now = datetime.now(UTC)

        # Validate config
        self._validate_config(config)

        # In production, save to database
        return {
            "id": strategy_id,
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "strategy_type": strategy_type,
            "status": StrategyStatus.DRAFT,
            "is_template": False,
            "current_version": 1,
            "config": config,
            "created_at": now,
            "updated_at": now,
        }

    async def get_strategy(
        self,
        strategy_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Get a strategy by ID."""
        # Simplified - in production use database
        return None

    async def list_strategies(
        self,
        tenant_id: UUID,
        status: StrategyStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List strategies for a tenant."""
        # Simplified - in production use database
        return [], 0

    async def update_strategy(
        self,
        strategy_id: UUID,
        tenant_id: UUID,
        **kwargs,
    ) -> dict[str, Any] | None:
        """Update a strategy (creates new version if config changes)."""
        # Simplified - in production use database
        return None

    async def delete_strategy(
        self,
        strategy_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Delete a strategy."""
        # Simplified - in production use database
        return False

    async def list_versions(
        self,
        strategy_id: UUID,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        """List all versions of a strategy."""
        # Simplified - in production use database
        return []

    async def get_version(
        self,
        strategy_id: UUID,
        version: int,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Get a specific version of a strategy."""
        # Simplified - in production use database
        return None

    async def clone_strategy(
        self,
        strategy_id: UUID,
        tenant_id: UUID,
        new_name: str,
    ) -> dict[str, Any] | None:
        """Clone a strategy with a new name."""
        original = await self.get_strategy(strategy_id, tenant_id)
        if not original:
            return None

        return await self.create_strategy(
            tenant_id=tenant_id,
            name=new_name,
            description=f"Cloned from: {original['name']}",
            strategy_type=original["strategy_type"],
            config=original["config"],
        )

    async def validate_strategy(
        self,
        strategy_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any]:
        """Validate a strategy configuration."""
        strategy = await self.get_strategy(strategy_id, tenant_id)
        if not strategy:
            return {"valid": False, "errors": ["Strategy not found"]}

        errors = []
        warnings = []

        config = strategy["config"]

        # Validate symbols
        if not config.symbols:
            errors.append("At least one symbol is required")

        # Validate indicators
        if not config.indicators:
            warnings.append("No indicators defined")

        # Validate entry conditions
        if not config.entry_conditions:
            errors.append("At least one entry condition is required")

        # Validate risk management
        if config.risk.stop_loss_percent and config.risk.stop_loss_percent > 50:
            warnings.append("Stop loss exceeds 50% - consider reducing")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def _validate_config(self, config: StrategyConfig) -> None:
        """Validate strategy configuration."""
        if not config.symbols:
            raise ValueError("At least one symbol is required")

        for symbol in config.symbols:
            if not symbol or len(symbol) > 10:
                raise ValueError(f"Invalid symbol: {symbol}")

        valid_timeframes = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
        if config.timeframe not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {config.timeframe}")


def get_strategy_service() -> StrategyService:
    """Dependency to get strategy service."""
    return StrategyService()
