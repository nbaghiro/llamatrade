"""Semantic validation for allocation-based strategy DSL."""

from __future__ import annotations

from dataclasses import dataclass, field

from llamatrade_dsl.ast import (
    COMPARISON_OPS,
    FILTER_CRITERIA,
    INDICATORS,
    LOGICAL_OPS,
    METRICS,
    REBALANCE_FREQUENCIES,
    WEIGHT_METHODS,
    Asset,
    Block,
    Comparison,
    Condition,
    Crossover,
    Filter,
    Group,
    If,
    Indicator,
    LogicalOp,
    Metric,
    NumericLiteral,
    Price,
    Strategy,
    Value,
    Weight,
)


def _find_similar(target: str, candidates: frozenset[str], max_results: int = 3) -> list[str]:
    """Find similar strings from candidates using simple edit distance heuristics.

    Args:
        target: The string to match
        candidates: Set of valid strings
        max_results: Maximum number of suggestions to return

    Returns:
        List of similar strings, sorted by similarity
    """
    if not target:
        return []

    target_lower = target.lower()
    scored: list[tuple[str, int]] = []

    for candidate in candidates:
        candidate_lower = candidate.lower()
        score = 0

        # Exact prefix match is very good
        if candidate_lower.startswith(target_lower):
            score += 100

        # Substring match is good
        if target_lower in candidate_lower or candidate_lower in target_lower:
            score += 50

        # Same length is slightly better
        if len(candidate) == len(target):
            score += 10

        # Count matching characters
        matching_chars = sum(1 for c in target_lower if c in candidate_lower)
        score += matching_chars * 2

        # Penalize length difference
        score -= abs(len(candidate) - len(target))

        if score > 0:
            scored.append((candidate, score))

    # Sort by score descending and return top results
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:max_results]]


@dataclass
class ValidationError:
    """A single validation error with optional location and suggestions.

    Attributes:
        message: The error message
        path: The AST path where the error occurred (e.g., "strategy.children[0].method")
        line: Line number in source (1-indexed, if available)
        column: Column number in source (1-indexed, if available)
        suggestions: List of suggested fixes or valid values
    """

    message: str
    path: str = ""
    line: int | None = None
    column: int | None = None
    suggestions: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = []

        # Add location if available
        if self.line is not None:
            if self.column is not None:
                parts.append(f"line {self.line}, column {self.column}")
            else:
                parts.append(f"line {self.line}")

        # Add path if available
        if self.path:
            parts.append(self.path)

        # Build message
        if parts:
            result = f"{': '.join(parts)}: {self.message}"
        else:
            result = self.message

        # Add suggestions
        if self.suggestions:
            result += f" (did you mean: {', '.join(self.suggestions[:3])}?)"

        return result


@dataclass
class ValidationResult:
    """Result of validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


class Validator:
    """Validates allocation strategy AST for semantic correctness."""

    def __init__(self) -> None:
        self.errors: list[ValidationError] = []

    def validate(self, strategy: Strategy) -> ValidationResult:
        """Validate a complete strategy definition."""
        self.errors = []
        self._validate_strategy(strategy, "strategy")
        return ValidationResult(valid=len(self.errors) == 0, errors=self.errors)

    def _validate_strategy(self, strategy: Strategy, path: str) -> None:
        """Validate a strategy node."""
        # Name is required
        if not strategy.name or not strategy.name.strip():
            self._error("Strategy name is required", f"{path}.name")

        # Validate rebalance frequency if present
        if strategy.rebalance and strategy.rebalance not in REBALANCE_FREQUENCIES:
            self._error(
                f"Invalid rebalance frequency: {strategy.rebalance}. "
                f"Valid options: {', '.join(sorted(REBALANCE_FREQUENCIES))}",
                f"{path}.rebalance",
            )

        # Must have at least one child block
        if not strategy.children:
            self._error("Strategy must have at least one allocation block", f"{path}.children")

        # Validate all children
        for i, child in enumerate(strategy.children):
            self._validate_block(child, f"{path}.children[{i}]")

    def _validate_block(self, block: Block, path: str) -> None:
        """Validate any block type."""
        match block:
            case Strategy():
                # Nested strategies not allowed
                self._error("Nested strategy blocks are not allowed", path)

            case Group():
                self._validate_group(block, path)

            case Weight():
                self._validate_weight(block, path)

            case Asset():
                self._validate_asset(block, path)

            case If():
                self._validate_if(block, path)

            case Filter():
                self._validate_filter(block, path)

    def _validate_group(self, group: Group, path: str) -> None:
        """Validate a group block."""
        if not group.name or not group.name.strip():
            self._error("Group name is required", f"{path}.name")

        if not group.children:
            self._error("Group must have at least one child block", f"{path}.children")

        for i, child in enumerate(group.children):
            self._validate_block(child, f"{path}.children[{i}]")

    def _validate_weight(self, weight: Weight, path: str) -> None:
        """Validate a weight block."""
        # Extract location if available
        loc = weight.location
        line = loc.line if loc else None
        col = loc.column if loc else None

        # Method must be valid
        if weight.method not in WEIGHT_METHODS:
            suggestions = _find_similar(weight.method, WEIGHT_METHODS)
            self._error(
                f"Invalid weight method: {weight.method}",
                f"{path}.method",
                line=line,
                column=col,
                suggestions=suggestions,
            )

        # Must have children
        if not weight.children:
            self._error("Weight block must have at least one child", f"{path}.children")

        # Validate lookback for dynamic methods
        dynamic_methods = {"momentum", "inverse-volatility", "min-variance", "risk-parity"}
        if weight.method in dynamic_methods:
            if weight.lookback is None:
                # Default lookback is ok, but explicit is preferred for clarity
                pass
            elif weight.lookback <= 0:
                self._error("Lookback must be a positive integer", f"{path}.lookback")

        # Validate top N selection
        if weight.top is not None:
            if weight.top <= 0:
                self._error("Top selection must be a positive integer", f"{path}.top")
            if weight.top > len(weight.children):
                child_count = len(weight.children)
                self._error(
                    f"Top selection ({weight.top}) exceeds children ({child_count})",
                    f"{path}.top",
                )

        # For specified method, validate weights sum to ~100
        if weight.method == "specified":
            total_weight = 0.0
            for i, child in enumerate(weight.children):
                if isinstance(child, Asset):
                    if child.weight is None:
                        self._error(
                            "Asset must have :weight when parent uses method: specified",
                            f"{path}.children[{i}]",
                        )
                    else:
                        total_weight += child.weight

            # Allow some tolerance for rounding
            if weight.children and abs(total_weight - 100.0) > 0.01:
                self._error(
                    f"Weights must sum to 100%, got {total_weight}%",
                    f"{path}.children",
                )

        # For non-specified methods, assets should NOT have weights
        else:
            for i, child in enumerate(weight.children):
                if isinstance(child, Asset) and child.weight is not None:
                    self._error(
                        f"Asset should not have :weight when parent uses method: {weight.method}",
                        f"{path}.children[{i}]",
                    )

        # Validate children
        for i, child in enumerate(weight.children):
            self._validate_block(child, f"{path}.children[{i}]")

    def _validate_asset(self, asset: Asset, path: str) -> None:
        """Validate an asset block."""
        if not asset.symbol or not asset.symbol.strip():
            self._error("Asset symbol is required", f"{path}.symbol")

        # Symbol should look like a valid ticker
        if asset.symbol and not asset.symbol[0].isalpha():
            self._error(
                f"Asset symbol must start with a letter: {asset.symbol}",
                f"{path}.symbol",
            )

        # Weight must be positive if present
        if asset.weight is not None and asset.weight <= 0:
            self._error("Asset weight must be positive", f"{path}.weight")

    def _validate_if(self, if_block: If, path: str) -> None:
        """Validate an if block."""
        # Validate condition
        self._validate_condition(if_block.condition, f"{path}.condition")

        # Validate then block
        self._validate_block(if_block.then_block, f"{path}.then")

        # Validate else block if present
        if if_block.else_block is not None:
            self._validate_block(if_block.else_block, f"{path}.else")

    def _validate_filter(self, filter_block: Filter, path: str) -> None:
        """Validate a filter block."""
        # Validate criteria
        if filter_block.by not in FILTER_CRITERIA:
            self._error(
                f"Invalid filter criteria: {filter_block.by}. "
                f"Valid options: {', '.join(sorted(FILTER_CRITERIA))}",
                f"{path}.by",
            )

        # Validate selection
        if filter_block.select_direction not in ("top", "bottom"):
            self._error(
                f"Invalid select direction: {filter_block.select_direction}. "
                "Must be 'top' or 'bottom'",
                f"{path}.select_direction",
            )

        if filter_block.select_count <= 0:
            self._error("Select count must be positive", f"{path}.select_count")

        # Validate lookback if present
        if filter_block.lookback is not None and filter_block.lookback <= 0:
            self._error("Lookback must be a positive integer", f"{path}.lookback")

        # Must have children
        if not filter_block.children:
            self._error("Filter block must have at least one child", f"{path}.children")

        # Selection count can't exceed available children (counting nested assets)
        asset_count = self._count_assets(filter_block.children)
        if filter_block.select_count > asset_count:
            select = filter_block.select_count
            self._error(
                f"Select count ({select}) exceeds available assets ({asset_count})",
                f"{path}.select_count",
            )

        # Validate children
        for i, child in enumerate(filter_block.children):
            self._validate_block(child, f"{path}.children[{i}]")

    def _count_assets(self, blocks: list[Block]) -> int:
        """Count total assets in a list of blocks (recursively)."""
        count = 0
        for block in blocks:
            if isinstance(block, Asset):
                count += 1
            elif isinstance(block, (Group, Weight, Filter)):
                count += self._count_assets(block.children)
            elif isinstance(block, If):
                count += self._count_assets([block.then_block])
                if block.else_block:
                    count += self._count_assets([block.else_block])
        return count

    def _validate_condition(self, condition: Condition, path: str) -> None:
        """Validate a condition expression."""
        match condition:
            case Comparison():
                self._validate_comparison(condition, path)

            case Crossover():
                self._validate_crossover(condition, path)

            case LogicalOp():
                self._validate_logical_op(condition, path)

    def _validate_comparison(self, comp: Comparison, path: str) -> None:
        """Validate a comparison condition."""
        if comp.operator not in COMPARISON_OPS:
            self._error(
                f"Invalid comparison operator: {comp.operator}. "
                f"Valid options: {', '.join(sorted(COMPARISON_OPS))}",
                f"{path}.operator",
            )

        self._validate_value(comp.left, f"{path}.left")
        self._validate_value(comp.right, f"{path}.right")

    def _validate_crossover(self, cross: Crossover, path: str) -> None:
        """Validate a crossover condition."""
        if cross.direction not in ("above", "below"):
            self._error(
                f"Invalid crossover direction: {cross.direction}. Must be 'above' or 'below'",
                f"{path}.direction",
            )

        self._validate_value(cross.fast, f"{path}.fast")
        self._validate_value(cross.slow, f"{path}.slow")

    def _validate_logical_op(self, op: LogicalOp, path: str) -> None:
        """Validate a logical operation."""
        if op.operator not in LOGICAL_OPS:
            self._error(
                f"Invalid logical operator: {op.operator}. "
                f"Valid options: {', '.join(sorted(LOGICAL_OPS))}",
                f"{path}.operator",
            )

        # Validate operand count
        if op.operator == "not":
            if len(op.operands) != 1:
                self._error("'not' requires exactly 1 operand", f"{path}.operands")
        elif op.operator in ("and", "or"):
            if len(op.operands) < 2:
                self._error(f"'{op.operator}' requires at least 2 operands", f"{path}.operands")

        # Validate each operand
        for i, operand in enumerate(op.operands):
            self._validate_condition(operand, f"{path}.operands[{i}]")

    def _validate_value(self, value: Value, path: str) -> None:
        """Validate a value expression."""
        match value:
            case NumericLiteral():
                pass  # Any number is valid

            case Price():
                self._validate_price(value, path)

            case Indicator():
                self._validate_indicator(value, path)

            case Metric():
                self._validate_metric(value, path)

    def _validate_price(self, price: Price, path: str) -> None:
        """Validate a price value."""
        if not price.symbol or not price.symbol.strip():
            self._error("Price symbol is required", f"{path}.symbol")

        if price.field not in ("close", "open", "high", "low", "volume"):
            self._error(
                f"Invalid price field: {price.field}. "
                "Valid options: close, open, high, low, volume",
                f"{path}.field",
            )

    def _validate_indicator(self, indicator: Indicator, path: str) -> None:
        """Validate an indicator value."""
        # Extract location if available
        loc = indicator.location
        line = loc.line if loc else None
        col = loc.column if loc else None

        if indicator.name not in INDICATORS:
            suggestions = _find_similar(indicator.name, INDICATORS)
            self._error(
                f"Unknown indicator: {indicator.name}",
                f"{path}.name",
                line=line,
                column=col,
                suggestions=suggestions,
            )

        if not indicator.symbol or not indicator.symbol.strip():
            self._error(
                "Indicator symbol is required",
                f"{path}.symbol",
                line=line,
                column=col,
            )

        # Validate params are positive
        for i, param in enumerate(indicator.params):
            if param <= 0:
                self._error(
                    f"Indicator parameter must be positive: {param}",
                    f"{path}.params[{i}]",
                    line=line,
                    column=col,
                )

    def _validate_metric(self, metric: Metric, path: str) -> None:
        """Validate a metric value."""
        if metric.name not in METRICS:
            self._error(
                f"Unknown metric: {metric.name}. Valid options: {', '.join(sorted(METRICS))}",
                f"{path}.name",
            )

        if not metric.symbol or not metric.symbol.strip():
            self._error("Metric symbol is required", f"{path}.symbol")

        if metric.period is not None and metric.period <= 0:
            self._error("Metric period must be positive", f"{path}.period")

    def _error(
        self,
        message: str,
        path: str,
        line: int | None = None,
        column: int | None = None,
        suggestions: list[str] | None = None,
    ) -> None:
        """Record a validation error.

        Args:
            message: The error message
            path: The AST path where the error occurred
            line: Line number (if known from source location)
            column: Column number (if known from source location)
            suggestions: List of suggested fixes
        """
        self.errors.append(
            ValidationError(
                message=message,
                path=path,
                line=line,
                column=column,
                suggestions=suggestions or [],
            )
        )


def validate(strategy: Strategy) -> ValidationResult:
    """Validate a strategy definition."""
    return Validator().validate(strategy)


def validate_strategy(strategy: Strategy) -> ValidationResult:
    """Validate a strategy definition (alias for validate)."""
    return validate(strategy)
