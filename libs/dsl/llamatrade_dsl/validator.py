"""Semantic validation for strategy AST."""

from __future__ import annotations

from dataclasses import dataclass, field

from llamatrade_dsl.ast import (
    PRICE_SYMBOLS,
    STRATEGY_TYPES,
    TIMEFRAMES,
    ASTNode,
    FunctionCall,
    Keyword,
    Literal,
    Strategy,
    Symbol,
)
from llamatrade_dsl.indicators import (
    INDICATORS,
    validate_indicator_output,
    validate_indicator_params,
)


@dataclass
class ValidationError:
    """A single validation error."""

    message: str
    path: str = ""

    def __str__(self) -> str:
        if self.path:
            return f"{self.path}: {self.message}"
        return self.message


@dataclass
class ValidationResult:
    """Result of validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# Comparison operators
COMPARATORS = {">", "<", ">=", "<=", "=", "!="}

# Logical operators with minimum argument counts
LOGICAL_OPS = {
    "and": {"min_args": 2},
    "or": {"min_args": 2},
    "not": {"min_args": 1, "max_args": 1},
}

# Crossover operators
CROSSOVER_OPS = {"cross-above", "cross-below"}

# Arithmetic operators
ARITHMETIC_OPS = {"+", "-", "*", "/", "abs", "min", "max"}

# Special functions
SPECIAL_OPS = {
    "prev": {"args": 2},  # (prev expr n) - value n bars ago
    "has-position": {"args": 0},
    "position-side": {"args": 0},
    "position-pnl-pct": {"args": 0},
    "time-between": {"args": 2},
    "day-of-week": {"min_args": 1},
    "market-hours": {"args": 0},
}


class Validator:
    """Validates AST nodes for semantic correctness."""

    def __init__(self):
        self.errors: list[ValidationError] = []

    def validate(self, node: ASTNode, path: str = "root") -> ValidationResult:
        """Validate an AST node."""
        self.errors = []
        self._validate_node(node, path)
        return ValidationResult(valid=len(self.errors) == 0, errors=self.errors)

    def validate_strategy(self, strategy: Strategy) -> ValidationResult:
        """Validate a complete strategy definition."""
        self.errors = []

        # Validate metadata
        if not strategy.name or not strategy.name.strip():
            self._error("Strategy name is required", "name")

        if not strategy.symbols:
            self._error("At least one symbol is required", "symbols")
        else:
            for i, symbol in enumerate(strategy.symbols):
                if not symbol or not isinstance(symbol, str):
                    self._error(f"Invalid symbol at index {i}", f"symbols[{i}]")

        if strategy.timeframe not in TIMEFRAMES:
            self._error(
                f"Invalid timeframe: {strategy.timeframe}. "
                f"Valid options: {', '.join(sorted(TIMEFRAMES))}",
                "timeframe",
            )

        if strategy.strategy_type not in STRATEGY_TYPES:
            self._error(
                f"Invalid strategy type: {strategy.strategy_type}. "
                f"Valid options: {', '.join(sorted(STRATEGY_TYPES))}",
                "type",
            )

        # Validate entry condition
        if strategy.entry is None:
            self._error("Entry condition is required", "entry")
        else:
            self._validate_condition(strategy.entry, "entry")

        # Validate exit condition
        if strategy.exit is None:
            self._error("Exit condition is required", "exit")
        else:
            self._validate_condition(strategy.exit, "exit")

        # Validate risk config
        self._validate_risk(strategy.risk)

        # Validate sizing config
        self._validate_sizing(strategy.sizing)

        return ValidationResult(valid=len(self.errors) == 0, errors=self.errors)

    def _validate_node(self, node: ASTNode, path: str) -> None:
        """Validate a single AST node."""
        match node:
            case Literal():
                pass  # Literals are always valid

            case Symbol(name=name):
                # Symbols should be price references or $-prefixed variables
                if name not in PRICE_SYMBOLS and not name.startswith("$"):
                    self._error(
                        f"Unknown symbol: {name}. "
                        f"Valid price symbols: {', '.join(sorted(PRICE_SYMBOLS))}",
                        path,
                    )

            case Keyword():
                pass  # Keywords are validated in context

            case FunctionCall(name=name, args=args):
                self._validate_function(name, args, path)

    def _validate_function(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate a function call."""
        fn_path = f"{path}.{name}"

        if name in INDICATORS:
            self._validate_indicator(name, args, fn_path)
        elif name in COMPARATORS:
            self._validate_comparator(name, args, fn_path)
        elif name in LOGICAL_OPS:
            self._validate_logical(name, args, fn_path)
        elif name in CROSSOVER_OPS:
            self._validate_crossover(name, args, fn_path)
        elif name in ARITHMETIC_OPS:
            self._validate_arithmetic(name, args, fn_path)
        elif name in SPECIAL_OPS:
            self._validate_special(name, args, fn_path)
        elif name == "strategy":
            pass  # Top-level, validated separately
        else:
            self._error(f"Unknown function: {name}", fn_path)

        # Recursively validate arguments
        for i, arg in enumerate(args):
            self._validate_node(arg, f"{fn_path}[{i}]")

    def _validate_indicator(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate indicator function call."""
        # Count positional args (excluding keywords)
        positional = [a for a in args if not isinstance(a, Keyword)]

        # Validate parameter count
        valid, error = validate_indicator_params(name, len(positional))
        if not valid and error:
            self._error(error, path)

        # Validate output selectors
        for arg in args:
            if isinstance(arg, Keyword):
                valid, error = validate_indicator_output(name, arg.name)
                if not valid and error:
                    self._error(error, path)

    def _validate_comparator(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate comparison operator."""
        if len(args) != 2:
            self._error(f"Comparator {name} requires exactly 2 arguments", path)

    def _validate_logical(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate logical operator."""
        spec = LOGICAL_OPS[name]
        min_args = spec.get("min_args", 1)
        max_args = spec.get("max_args")

        if len(args) < min_args:
            self._error(f"{name} requires at least {min_args} arguments", path)
        elif max_args is not None and len(args) > max_args:
            self._error(f"{name} accepts at most {max_args} arguments", path)

    def _validate_crossover(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate crossover operator."""
        if len(args) != 2:
            self._error(f"{name} requires exactly 2 arguments", path)

    def _validate_arithmetic(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate arithmetic operator."""
        if name == "abs" and len(args) != 1:
            self._error("abs requires exactly 1 argument", path)
        elif name in ("-", "/") and len(args) != 2:
            self._error(f"{name} requires exactly 2 arguments", path)
        elif name in ("+", "*", "min", "max") and len(args) < 2:
            self._error(f"{name} requires at least 2 arguments", path)

    def _validate_special(self, name: str, args: tuple[ASTNode, ...], path: str) -> None:
        """Validate special function."""
        spec = SPECIAL_OPS[name]

        if "args" in spec and len(args) != spec["args"]:
            self._error(f"{name} requires exactly {spec['args']} arguments", path)
        elif "min_args" in spec and len(args) < spec["min_args"]:
            self._error(f"{name} requires at least {spec['min_args']} arguments", path)

    def _validate_condition(self, node: ASTNode, path: str) -> None:
        """Validate that a node is a valid boolean condition."""
        if isinstance(node, FunctionCall):
            # Must be a comparison, logical, or crossover operator
            if node.name in COMPARATORS | set(LOGICAL_OPS.keys()) | CROSSOVER_OPS:
                self._validate_function(node.name, node.args, path)
            elif node.name in SPECIAL_OPS:
                # Some special ops return boolean
                if node.name in ("has-position", "market-hours"):
                    pass
                else:
                    self._error(
                        f"Function {node.name} does not return a boolean condition",
                        path,
                    )
            else:
                self._error(
                    f"Expected condition (comparison, logical, or crossover), "
                    f"got function: {node.name}",
                    path,
                )
        elif isinstance(node, Literal) and isinstance(node.value, bool):
            pass  # Boolean literals are valid conditions
        else:
            self._error(f"Expected condition expression, got {type(node).__name__}", path)

    def _validate_risk(self, risk: dict) -> None:
        """Validate risk configuration."""
        if not risk:
            return

        if "stop_loss_pct" in risk:
            val = risk["stop_loss_pct"]
            if val is not None and not (0 < val <= 100):
                self._error(
                    "stop_loss_pct must be between 0 and 100 (exclusive/inclusive)",
                    "risk.stop_loss_pct",
                )

        if "take_profit_pct" in risk:
            val = risk["take_profit_pct"]
            if val is not None and not (0 < val <= 1000):
                self._error(
                    "take_profit_pct must be between 0 and 1000 (exclusive/inclusive)",
                    "risk.take_profit_pct",
                )

        if "trailing_stop_pct" in risk:
            val = risk["trailing_stop_pct"]
            if val is not None and not (0 < val <= 50):
                self._error(
                    "trailing_stop_pct must be between 0 and 50 (exclusive/inclusive)",
                    "risk.trailing_stop_pct",
                )

        if "max_positions" in risk:
            val = risk["max_positions"]
            if val is not None and (not isinstance(val, int) or val < 1):
                self._error("max_positions must be a positive integer", "risk.max_positions")

        if "max_position_size_pct" in risk:
            val = risk["max_position_size_pct"]
            if val is not None and not (0 < val <= 100):
                self._error(
                    "max_position_size_pct must be between 0 and 100",
                    "risk.max_position_size_pct",
                )

    def _validate_sizing(self, sizing: dict) -> None:
        """Validate position sizing configuration."""
        if not sizing:
            return

        valid_types = {"percent-equity", "fixed-quantity", "risk-based"}
        sizing_type = sizing.get("type", "percent-equity")

        if sizing_type not in valid_types:
            self._error(
                f"Invalid sizing type: {sizing_type}. Valid options: {', '.join(valid_types)}",
                "sizing.type",
            )

        value = sizing.get("value")
        if value is not None:
            if sizing_type == "percent-equity" and not (0 < value <= 100):
                self._error(
                    "For percent-equity sizing, value must be between 0 and 100",
                    "sizing.value",
                )
            elif sizing_type == "fixed-quantity" and value <= 0:
                self._error(
                    "For fixed-quantity sizing, value must be positive",
                    "sizing.value",
                )

    def _error(self, message: str, path: str) -> None:
        """Record a validation error."""
        self.errors.append(ValidationError(message, path))


def validate(node: ASTNode) -> ValidationResult:
    """Validate an AST node."""
    return Validator().validate(node)


def validate_strategy(strategy: Strategy) -> ValidationResult:
    """Validate a strategy definition."""
    return Validator().validate_strategy(strategy)
