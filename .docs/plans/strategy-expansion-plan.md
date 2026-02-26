# Strategy System Expansion Plan

> Comprehensive implementation plan for the full strategy pipeline: DSL, database, compiler, backtest integration, live trading, and monitoring.

**Decision:** S-expression as canonical DSL format (per discussion)
**Scope:** Backend-only (frontend visual builder handled separately)
**Reference Docs:**
- `.docs/strategy-dsl-implementation.md` - Grammar and parser specs
- `.docs/strategy-dsl-options.md` - DSL approach analysis
- `.docs/architecture.md` - Service architecture

---

## Table of Contents

1. [Phase 1: DSL & Data Model](#phase-1-dsl--data-model)
2. [Phase 2: Strategy Compiler](#phase-2-strategy-compiler)
3. [Phase 3: Backtest Integration](#phase-3-backtest-integration)
4. [Phase 4: Live Trading Pipeline](#phase-4-live-trading-pipeline)
5. [Phase 5: Monitoring & Risk](#phase-5-monitoring--risk)
6. [Implementation Order](#implementation-order)
7. [Testing Strategy](#testing-strategy)

---

## Phase 1: DSL & Data Model

**Goal:** Establish the canonical strategy representation and persistence layer.

### 1.1 S-Expression DSL Core

**Location:** `libs/dsl/` (new shared library)

```
libs/dsl/
├── pyproject.toml
├── src/
│   └── llamatrade_dsl/
│       ├── __init__.py
│       ├── parser.py          # S-expr string → AST
│       ├── serializer.py      # AST → S-expr string
│       ├── ast.py             # AST node dataclasses
│       ├── validator.py       # Semantic validation
│       ├── to_json.py         # AST → JSON for DB storage
│       ├── from_json.py       # JSON → AST for loading
│       └── indicators.py      # Indicator registry & metadata
└── tests/
    ├── test_parser.py
    ├── test_serializer.py
    ├── test_validator.py
    └── test_roundtrip.py
```

#### AST Node Types

```python
# libs/dsl/src/llamatrade_dsl/ast.py

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

class NodeType(Enum):
    LITERAL = "literal"
    SYMBOL = "symbol"
    KEYWORD = "keyword"
    FUNCTION_CALL = "function_call"
    STRATEGY = "strategy"

@dataclass
class Literal:
    """Numeric or string literal."""
    value: int | float | str | bool
    node_type: NodeType = field(default=NodeType.LITERAL, init=False)

@dataclass
class Symbol:
    """Reference to price data: close, open, high, low, volume."""
    name: str
    node_type: NodeType = field(default=NodeType.SYMBOL, init=False)

@dataclass
class Keyword:
    """Keyword argument: :line, :signal, :upper."""
    name: str
    node_type: NodeType = field(default=NodeType.KEYWORD, init=False)

@dataclass
class FunctionCall:
    """Function invocation: (sma close 20), (and cond1 cond2)."""
    name: str
    args: list["ASTNode"]
    node_type: NodeType = field(default=NodeType.FUNCTION_CALL, init=False)

@dataclass
class Strategy:
    """Top-level strategy definition."""
    name: str
    description: str | None
    strategy_type: str
    symbols: list[str]
    timeframe: str
    entry: "ASTNode"
    exit: "ASTNode"
    sizing: dict[str, Any]
    risk: dict[str, Any]
    node_type: NodeType = field(default=NodeType.STRATEGY, init=False)

ASTNode = Literal | Symbol | Keyword | FunctionCall | Strategy
```

#### Parser Implementation

```python
# libs/dsl/src/llamatrade_dsl/parser.py

import re
from .ast import Literal, Symbol, Keyword, FunctionCall, Strategy, ASTNode

class ParseError(Exception):
    """Raised when parsing fails."""
    def __init__(self, message: str, position: int = 0):
        self.position = position
        super().__init__(f"{message} at position {position}")

class SExprParser:
    """
    Recursive descent parser for S-expressions.

    Supports:
    - Numbers: 42, 3.14, -5
    - Strings: "hello"
    - Symbols: close, open, high, low, volume
    - Keywords: :line, :signal
    - Function calls: (sma close 20)
    - Nested expressions: (and (> (rsi close 14) 70) (< price 100))
    """

    TOKEN_PATTERN = re.compile(
        r'''
        (?P<LPAREN>\()|
        (?P<RPAREN>\))|
        (?P<LBRACKET>\[)|
        (?P<RBRACKET>\])|
        (?P<LBRACE>\{)|
        (?P<RBRACE>\})|
        (?P<STRING>"[^"]*")|
        (?P<KEYWORD>:[a-zA-Z_][a-zA-Z0-9_-]*)|
        (?P<NUMBER>-?[0-9]+\.?[0-9]*)|
        (?P<SYMBOL>[a-zA-Z_][a-zA-Z0-9_-]*)|
        (?P<SKIP>\s+)|
        (?P<COMMENT>;[^\n]*)
        ''',
        re.VERBOSE
    )

    def __init__(self, source: str):
        self.source = source
        self.tokens = self._tokenize()
        self.pos = 0

    def _tokenize(self) -> list[tuple[str, str, int]]:
        tokens = []
        for match in self.TOKEN_PATTERN.finditer(self.source):
            kind = match.lastgroup
            value = match.group()
            if kind not in ('SKIP', 'COMMENT'):
                tokens.append((kind, value, match.start()))
        return tokens

    def parse(self) -> ASTNode:
        """Parse the source and return AST."""
        result = self._parse_expr()
        if self.pos < len(self.tokens):
            raise ParseError("Unexpected tokens after expression", self.tokens[self.pos][2])
        return result

    def parse_strategy(self) -> Strategy:
        """Parse a (strategy ...) definition."""
        node = self.parse()
        if not isinstance(node, FunctionCall) or node.name != "strategy":
            raise ParseError("Expected (strategy ...) definition")
        return self._build_strategy(node)

    def _parse_expr(self) -> ASTNode:
        if self.pos >= len(self.tokens):
            raise ParseError("Unexpected end of input")

        kind, value, position = self.tokens[self.pos]

        if kind == 'LPAREN':
            return self._parse_list()
        elif kind == 'NUMBER':
            self.pos += 1
            if '.' in value:
                return Literal(float(value))
            return Literal(int(value))
        elif kind == 'STRING':
            self.pos += 1
            return Literal(value[1:-1])  # Strip quotes
        elif kind == 'KEYWORD':
            self.pos += 1
            return Keyword(value[1:])  # Strip colon
        elif kind == 'SYMBOL':
            self.pos += 1
            return Symbol(value)
        elif kind == 'LBRACKET':
            return self._parse_vector()
        else:
            raise ParseError(f"Unexpected token: {value}", position)

    def _parse_list(self) -> FunctionCall:
        """Parse (fn arg1 arg2 ...)."""
        self._expect('LPAREN')

        if self.pos >= len(self.tokens):
            raise ParseError("Unexpected end of input in list")

        # First element is function name
        kind, value, pos = self.tokens[self.pos]
        if kind != 'SYMBOL':
            raise ParseError(f"Expected function name, got {value}", pos)
        self.pos += 1
        fn_name = value

        # Parse arguments
        args = []
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] != 'RPAREN':
            args.append(self._parse_expr())

        self._expect('RPAREN')
        return FunctionCall(fn_name, args)

    def _parse_vector(self) -> Literal:
        """Parse [item1 item2 ...] as a list literal."""
        self._expect('LBRACKET')
        items = []
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] != 'RBRACKET':
            node = self._parse_expr()
            if isinstance(node, Literal):
                items.append(node.value)
            elif isinstance(node, Symbol):
                items.append(node.name)
            else:
                raise ParseError("Vector elements must be literals or symbols")
        self._expect('RBRACKET')
        return Literal(items)

    def _expect(self, kind: str) -> str:
        if self.pos >= len(self.tokens):
            raise ParseError(f"Expected {kind}, got end of input")
        actual_kind, value, pos = self.tokens[self.pos]
        if actual_kind != kind:
            raise ParseError(f"Expected {kind}, got {actual_kind}", pos)
        self.pos += 1
        return value

    def _build_strategy(self, node: FunctionCall) -> Strategy:
        """Convert parsed (strategy ...) to Strategy object."""
        # Extract keyword arguments
        kwargs = {}
        i = 0
        while i < len(node.args):
            arg = node.args[i]
            if isinstance(arg, Keyword):
                if i + 1 < len(node.args):
                    kwargs[arg.name] = node.args[i + 1]
                    i += 2
                else:
                    raise ParseError(f"Missing value for keyword :{arg.name}")
            else:
                i += 1

        # Extract required fields
        def get_literal(key: str, default=None):
            val = kwargs.get(key)
            if val is None:
                return default
            if isinstance(val, Literal):
                return val.value
            return val

        def get_node(key: str) -> ASTNode | None:
            return kwargs.get(key)

        return Strategy(
            name=get_literal("name", "Unnamed"),
            description=get_literal("description"),
            strategy_type=get_literal("type", "custom"),
            symbols=get_literal("symbols", []),
            timeframe=get_literal("timeframe", "1D"),
            entry=get_node("entry"),
            exit=get_node("exit"),
            sizing={"type": "percent-equity", "value": get_literal("position-size", 10)},
            risk={
                "stop_loss_pct": get_literal("stop-loss-pct"),
                "take_profit_pct": get_literal("take-profit-pct"),
                "max_positions": get_literal("max-positions", 10),
            }
        )


def parse(source: str) -> ASTNode:
    """Parse S-expression string to AST."""
    return SExprParser(source).parse()

def parse_strategy(source: str) -> Strategy:
    """Parse strategy definition to Strategy object."""
    return SExprParser(source).parse_strategy()
```

#### Validator Implementation

```python
# libs/dsl/src/llamatrade_dsl/validator.py

from dataclasses import dataclass
from .ast import ASTNode, FunctionCall, Symbol, Literal, Keyword, Strategy

@dataclass
class ValidationError:
    message: str
    path: str = ""

@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError]

# Known indicators and their parameter counts
INDICATORS = {
    "sma": {"params": (2,), "outputs": ["value"]},
    "ema": {"params": (2,), "outputs": ["value"]},
    "rsi": {"params": (2,), "outputs": ["value"]},
    "macd": {"params": (4,), "outputs": ["line", "signal", "histogram"]},
    "bbands": {"params": (3,), "outputs": ["upper", "middle", "lower"]},
    "atr": {"params": (2,), "outputs": ["value"]},
    "adx": {"params": (2,), "outputs": ["value", "plus_di", "minus_di"]},
    "stoch": {"params": (4,), "outputs": ["k", "d"]},
    "cci": {"params": (2,), "outputs": ["value"]},
    "williams_r": {"params": (2,), "outputs": ["value"]},
    "obv": {"params": (1,), "outputs": ["value"]},
    "mfi": {"params": (2,), "outputs": ["value"]},
    "vwap": {"params": (1,), "outputs": ["value"]},
    "keltner": {"params": (3,), "outputs": ["upper", "middle", "lower"]},
    "donchian": {"params": (2,), "outputs": ["upper", "lower"]},
}

# Logical/comparison operators
OPERATORS = {
    "and": {"min_args": 2},
    "or": {"min_args": 2},
    "not": {"args": 1},
    ">": {"args": 2},
    "<": {"args": 2},
    ">=": {"args": 2},
    "<=": {"args": 2},
    "=": {"args": 2},
    "cross-above": {"args": 2},
    "cross-below": {"args": 2},
}

# Arithmetic operators
ARITHMETIC = {"+", "-", "*", "/", "abs", "min", "max"}

# Valid price references
PRICE_SYMBOLS = {"close", "open", "high", "low", "volume", "timestamp"}

# Valid timeframes
TIMEFRAMES = {"1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"}


class Validator:
    """Validates AST for semantic correctness."""

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
        if not strategy.name:
            self._error("Strategy name is required", "name")

        if not strategy.symbols:
            self._error("At least one symbol is required", "symbols")

        if strategy.timeframe not in TIMEFRAMES:
            self._error(f"Invalid timeframe: {strategy.timeframe}", "timeframe")

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
        if strategy.risk:
            self._validate_risk(strategy.risk)

        return ValidationResult(valid=len(self.errors) == 0, errors=self.errors)

    def _validate_node(self, node: ASTNode, path: str):
        match node:
            case Literal():
                pass  # Literals are always valid
            case Symbol(name=name):
                if name not in PRICE_SYMBOLS and not name.startswith("$"):
                    self._error(f"Unknown symbol: {name}", path)
            case Keyword():
                pass  # Keywords validated in context
            case FunctionCall(name=name, args=args):
                self._validate_function(name, args, path)

    def _validate_function(self, name: str, args: list[ASTNode], path: str):
        if name in INDICATORS:
            self._validate_indicator(name, args, path)
        elif name in OPERATORS:
            self._validate_operator(name, args, path)
        elif name in ARITHMETIC:
            for i, arg in enumerate(args):
                self._validate_node(arg, f"{path}.{name}[{i}]")
        elif name == "prev":
            if len(args) != 2:
                self._error("prev requires 2 arguments: (prev expr n)", path)
        elif name == "strategy":
            pass  # Top-level, validated separately
        else:
            self._error(f"Unknown function: {name}", path)

    def _validate_indicator(self, name: str, args: list[ASTNode], path: str):
        spec = INDICATORS[name]
        expected = spec["params"][0]

        # Check argument count (excluding keyword args)
        positional = [a for a in args if not isinstance(a, Keyword)]
        if len(positional) != expected:
            self._error(
                f"{name} expects {expected} arguments, got {len(positional)}",
                path
            )

        # Validate each argument
        for i, arg in enumerate(args):
            self._validate_node(arg, f"{path}.{name}[{i}]")

    def _validate_operator(self, name: str, args: list[ASTNode], path: str):
        spec = OPERATORS[name]

        if "args" in spec and len(args) != spec["args"]:
            self._error(f"{name} requires {spec['args']} arguments", path)
        elif "min_args" in spec and len(args) < spec["min_args"]:
            self._error(f"{name} requires at least {spec['min_args']} arguments", path)

        for i, arg in enumerate(args):
            self._validate_node(arg, f"{path}.{name}[{i}]")

    def _validate_condition(self, node: ASTNode, path: str):
        """Validate that a node is a valid boolean condition."""
        if isinstance(node, FunctionCall):
            if node.name in OPERATORS:
                self._validate_operator(node.name, node.args, path)
            else:
                self._error(f"Expected condition, got function: {node.name}", path)
        else:
            self._error(f"Expected condition expression", path)

    def _validate_risk(self, risk: dict):
        if risk.get("stop_loss_pct") is not None:
            val = risk["stop_loss_pct"]
            if not (0 < val <= 100):
                self._error("stop_loss_pct must be between 0 and 100", "risk.stop_loss_pct")

        if risk.get("take_profit_pct") is not None:
            val = risk["take_profit_pct"]
            if not (0 < val <= 1000):
                self._error("take_profit_pct must be between 0 and 1000", "risk.take_profit_pct")

    def _error(self, message: str, path: str):
        self.errors.append(ValidationError(message, path))


def validate(node: ASTNode) -> ValidationResult:
    """Validate an AST node."""
    return Validator().validate(node)

def validate_strategy(strategy: Strategy) -> ValidationResult:
    """Validate a strategy definition."""
    return Validator().validate_strategy(strategy)
```

### 1.2 SQLAlchemy Database Models

**Location:** `libs/db/src/llamatrade_db/models/strategy.py`

```python
# libs/db/src/llamatrade_db/models/strategy.py

from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID, uuid4
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, Enum, JSON, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class StrategyType(PyEnum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"


class StrategyStatus(PyEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Strategy(Base):
    """Strategy metadata (name, status, type). Config stored in versions."""
    __tablename__ = "strategies"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    strategy_type: Mapped[StrategyType] = mapped_column(Enum(StrategyType), default=StrategyType.CUSTOM)
    status: Mapped[StrategyStatus] = mapped_column(Enum(StrategyStatus), default=StrategyStatus.DRAFT)

    current_version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # Relationships
    versions: Mapped[list["StrategyVersion"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_strategies_tenant_status", "tenant_id", "status"),
        Index("ix_strategies_tenant_type", "tenant_id", "strategy_type"),
    )


class StrategyVersion(Base):
    """Immutable strategy configuration snapshot."""
    __tablename__ = "strategy_versions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # S-expression source (canonical format)
    config_sexpr: Mapped[str] = mapped_column(Text, nullable=False)

    # Parsed JSON for querying (denormalized)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Denormalized for filtering
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
        Index("ix_strategy_versions_symbols", "symbols", postgresql_using="gin"),
    )


class DeploymentStatus(PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class DeploymentEnvironment(PyEnum):
    PAPER = "paper"
    LIVE = "live"


class StrategyDeployment(Base):
    """Links a strategy version to live/paper trading."""
    __tablename__ = "strategy_deployments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    strategy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    environment: Mapped[DeploymentEnvironment] = mapped_column(Enum(DeploymentEnvironment), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(Enum(DeploymentStatus), default=DeploymentStatus.PENDING)

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Runtime configuration overrides
    config_override: Mapped[dict | None] = mapped_column(JSONB)

    # Error info if status is ERROR
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_deployments_tenant_status", "tenant_id", "status"),
    )
```

### 1.3 Strategy Service Implementation

**Location:** `services/strategy/src/services/strategy_service.py`

```python
# services/strategy/src/services/strategy_service.py

from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.strategy import (
    Strategy, StrategyVersion, StrategyStatus, StrategyType
)
from llamatrade_dsl import parse_strategy, validate_strategy, to_json
from ..models import (
    StrategyCreate, StrategyUpdate, StrategyResponse,
    StrategyDetailResponse, StrategyVersionResponse
)


class StrategyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_strategy(
        self,
        tenant_id: UUID,
        user_id: UUID,
        data: StrategyCreate,
    ) -> StrategyDetailResponse:
        """Create a new strategy with initial version."""
        # Parse and validate S-expression
        ast = parse_strategy(data.config_sexpr)
        validation = validate_strategy(ast)
        if not validation.valid:
            raise ValueError(f"Invalid strategy: {validation.errors}")

        # Create strategy record
        strategy = Strategy(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            strategy_type=StrategyType(ast.strategy_type),
            status=StrategyStatus.DRAFT,
            current_version=1,
            created_by=user_id,
        )
        self.db.add(strategy)
        await self.db.flush()

        # Create version 1
        version = StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            config_sexpr=data.config_sexpr,
            config_json=to_json(ast),
            symbols=ast.symbols,
            timeframe=ast.timeframe,
            created_by=user_id,
        )
        self.db.add(version)
        await self.db.commit()

        return self._to_detail_response(strategy, version)

    async def get_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> StrategyDetailResponse | None:
        """Get strategy with current version config."""
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id)
            .where(Strategy.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        strategy = result.scalar_one_or_none()

        if not strategy:
            return None

        version = await self._get_version(strategy.id, strategy.current_version)
        return self._to_detail_response(strategy, version)

    async def list_strategies(
        self,
        tenant_id: UUID,
        status: StrategyStatus | None = None,
        strategy_type: StrategyType | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StrategyResponse], int]:
        """List strategies with pagination."""
        stmt = select(Strategy).where(Strategy.tenant_id == tenant_id)

        if status:
            stmt = stmt.where(Strategy.status == status)
        if strategy_type:
            stmt = stmt.where(Strategy.strategy_type == strategy_type)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar()

        # Paginate
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        strategies = result.scalars().all()

        return [self._to_response(s) for s in strategies], total

    async def update_strategy(
        self,
        tenant_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        data: StrategyUpdate,
    ) -> StrategyDetailResponse | None:
        """Update strategy. Creates new version if config changes."""
        strategy = await self._get_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        # Update metadata fields
        if data.name is not None:
            strategy.name = data.name
        if data.description is not None:
            strategy.description = data.description
        if data.status is not None:
            strategy.status = data.status

        # If config changed, create new version
        if data.config_sexpr is not None:
            ast = parse_strategy(data.config_sexpr)
            validation = validate_strategy(ast)
            if not validation.valid:
                raise ValueError(f"Invalid strategy: {validation.errors}")

            new_version_num = strategy.current_version + 1
            version = StrategyVersion(
                strategy_id=strategy.id,
                version=new_version_num,
                config_sexpr=data.config_sexpr,
                config_json=to_json(ast),
                symbols=ast.symbols,
                timeframe=ast.timeframe,
                created_by=user_id,
            )
            self.db.add(version)
            strategy.current_version = new_version_num

        await self.db.commit()

        version = await self._get_version(strategy.id, strategy.current_version)
        return self._to_detail_response(strategy, version)

    async def delete_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> bool:
        """Soft delete (archive) a strategy."""
        strategy = await self._get_by_id(tenant_id, strategy_id)
        if not strategy:
            return False

        strategy.status = StrategyStatus.ARCHIVED
        await self.db.commit()
        return True

    async def list_versions(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> list[StrategyVersionResponse]:
        """List all versions of a strategy."""
        # Verify tenant owns strategy
        strategy = await self._get_by_id(tenant_id, strategy_id)
        if not strategy:
            return []

        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
        )
        result = await self.db.execute(stmt)
        versions = result.scalars().all()

        return [self._to_version_response(v) for v in versions]

    async def get_version(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
        version: int,
    ) -> StrategyVersionResponse | None:
        """Get a specific version of a strategy."""
        strategy = await self._get_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        v = await self._get_version(strategy_id, version)
        return self._to_version_response(v) if v else None

    # --- Private helpers ---

    async def _get_by_id(self, tenant_id: UUID, strategy_id: UUID) -> Strategy | None:
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id)
            .where(Strategy.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_version(self, strategy_id: UUID, version: int) -> StrategyVersion | None:
        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _to_response(self, s: Strategy) -> StrategyResponse:
        return StrategyResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            strategy_type=s.strategy_type.value,
            status=s.status.value,
            current_version=s.current_version,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    def _to_detail_response(self, s: Strategy, v: StrategyVersion) -> StrategyDetailResponse:
        return StrategyDetailResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            strategy_type=s.strategy_type.value,
            status=s.status.value,
            current_version=s.current_version,
            created_at=s.created_at,
            updated_at=s.updated_at,
            config_sexpr=v.config_sexpr,
            config_json=v.config_json,
            symbols=v.symbols,
            timeframe=v.timeframe,
        )

    def _to_version_response(self, v: StrategyVersion) -> StrategyVersionResponse:
        return StrategyVersionResponse(
            version=v.version,
            config_sexpr=v.config_sexpr,
            symbols=v.symbols,
            timeframe=v.timeframe,
            created_at=v.created_at,
        )
```

### 1.4 Phase 1 Deliverables Checklist

| Item | Location | Status |
|------|----------|--------|
| S-expr parser | `libs/dsl/src/llamatrade_dsl/parser.py` | TODO |
| AST node types | `libs/dsl/src/llamatrade_dsl/ast.py` | TODO |
| AST serializer | `libs/dsl/src/llamatrade_dsl/serializer.py` | TODO |
| AST validator | `libs/dsl/src/llamatrade_dsl/validator.py` | TODO |
| JSON converter | `libs/dsl/src/llamatrade_dsl/to_json.py` | TODO |
| Strategy model | `libs/db/src/llamatrade_db/models/strategy.py` | TODO |
| StrategyVersion model | `libs/db/src/llamatrade_db/models/strategy.py` | TODO |
| StrategyDeployment model | `libs/db/src/llamatrade_db/models/strategy.py` | TODO |
| Alembic migration | `libs/db/migrations/versions/xxx_add_strategy_tables.py` | TODO |
| Strategy service | `services/strategy/src/services/strategy_service.py` | TODO |
| Parser unit tests | `libs/dsl/tests/test_parser.py` | TODO |
| Validator unit tests | `libs/dsl/tests/test_validator.py` | TODO |
| Service integration tests | `services/strategy/tests/test_strategy_service.py` | TODO |

---

## Phase 2: Strategy Compiler

**Goal:** Transform validated AST into executable runtime logic.

### 2.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    COMPILATION PIPELINE                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Strategy AST                                              │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              INDICATOR EXTRACTOR                     │  │
│   │   Walk AST → collect all indicator calls             │  │
│   │   Deduplicate → determine computation order          │  │
│   │   Calculate warmup period                            │  │
│   └─────────────────────────────────────────────────────┘  │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              INDICATOR PIPELINE                      │  │
│   │   For each indicator spec:                           │  │
│   │   - Get calculator from indicator library            │  │
│   │   - Wrap with caching                                │  │
│   │   Produces: bars → Dict[str, np.ndarray]             │  │
│   └─────────────────────────────────────────────────────┘  │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              CONDITION COMPILER                      │  │
│   │   AST → Callable[[EvalState], bool]                  │  │
│   │   Entry condition evaluator                          │  │
│   │   Exit condition evaluator                           │  │
│   └─────────────────────────────────────────────────────┘  │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              SIGNAL GENERATOR                        │  │
│   │   Combines entry/exit evaluators                     │  │
│   │   Applies position awareness                         │  │
│   │   Attaches stop-loss/take-profit                     │  │
│   └─────────────────────────────────────────────────────┘  │
│        │                                                    │
│        ▼                                                    │
│   CompiledStrategy                                          │
│   - warmup_bars: int                                        │
│   - on_bar(symbol, bars, position) → Signal | None          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 File Structure

**Location:** `services/strategy/src/compiler/`

```
services/strategy/src/compiler/
├── __init__.py
├── compiler.py         # Main compile() function
├── extractor.py        # Extract indicator specs from AST
├── pipeline.py         # IndicatorPipeline class
├── evaluator.py        # ConditionEvaluator class
├── signal.py           # SignalGenerator class
├── compiled.py         # CompiledStrategy class
└── state.py            # EvaluationState dataclass
```

### 2.3 Core Components

#### Indicator Extractor

```python
# services/strategy/src/compiler/extractor.py

from dataclasses import dataclass
from llamatrade_dsl.ast import ASTNode, FunctionCall, Symbol
from llamatrade_dsl.validator import INDICATORS

@dataclass
class IndicatorSpec:
    """Specification for an indicator to compute."""
    indicator_type: str      # sma, ema, rsi, etc.
    source: str              # close, high, volume, etc.
    params: tuple            # (period,) or (fast, slow, signal)
    output_key: str          # Unique cache key: "sma_close_20"
    output_field: str | None # For multi-output: "line", "upper", etc.
    required_bars: int       # Minimum history needed

def extract_indicators(entry_ast: ASTNode, exit_ast: ASTNode) -> list[IndicatorSpec]:
    """Extract all indicator specifications from entry/exit conditions."""
    specs: dict[str, IndicatorSpec] = {}

    def walk(node: ASTNode):
        if isinstance(node, FunctionCall):
            if node.name in INDICATORS:
                spec = _make_spec(node)
                specs[spec.output_key] = spec
            for arg in node.args:
                walk(arg)

    walk(entry_ast)
    walk(exit_ast)

    return list(specs.values())

def _make_spec(node: FunctionCall) -> IndicatorSpec:
    """Convert indicator function call to IndicatorSpec."""
    name = node.name
    args = node.args

    # First arg is usually source (close, high, etc.)
    source = "close"
    if args and isinstance(args[0], Symbol):
        source = args[0].name

    # Extract numeric params
    params = tuple(
        arg.value for arg in args
        if hasattr(arg, 'value') and isinstance(arg.value, (int, float))
    )

    # Check for output field selector (:line, :upper, etc.)
    output_field = None
    for arg in args:
        if hasattr(arg, 'name') and isinstance(arg, Keyword):
            output_field = arg.name

    # Calculate required bars
    required_bars = _calc_required_bars(name, params)

    # Generate unique key
    output_key = f"{name}_{source}_{'_'.join(map(str, params))}"
    if output_field:
        output_key += f"_{output_field}"

    return IndicatorSpec(
        indicator_type=name,
        source=source,
        params=params,
        output_key=output_key,
        output_field=output_field,
        required_bars=required_bars,
    )

def _calc_required_bars(indicator: str, params: tuple) -> int:
    """Calculate minimum bars needed for indicator warmup."""
    match indicator:
        case "sma" | "ema":
            return params[0] if params else 20
        case "rsi":
            return (params[0] if params else 14) + 1
        case "macd":
            slow = params[1] if len(params) > 1 else 26
            signal = params[2] if len(params) > 2 else 9
            return slow + signal
        case "bbands":
            return params[0] if params else 20
        case "atr" | "adx":
            return (params[0] if params else 14) + 1
        case "stoch":
            return (params[0] if params else 14) + (params[1] if len(params) > 1 else 3)
        case _:
            return 50  # Safe default
```

#### Condition Evaluator

```python
# services/strategy/src/compiler/evaluator.py

from typing import Any, Callable
from llamatrade_dsl.ast import ASTNode, FunctionCall, Symbol, Literal, Keyword
from .state import EvaluationState

class ConditionEvaluator:
    """Evaluates AST conditions against runtime state."""

    def __init__(self, ast: ASTNode):
        self.ast = ast
        self._compiled: Callable[[EvaluationState], bool] | None = None

    def evaluate(self, state: EvaluationState) -> bool:
        """Evaluate the condition tree."""
        return self._eval(self.ast, state)

    def _eval(self, node: ASTNode, state: EvaluationState) -> Any:
        match node:
            case Literal(value=v):
                return v

            case Symbol(name=name):
                return state.get_value(name)

            case FunctionCall(name="and", args=args):
                return all(self._eval(arg, state) for arg in args)

            case FunctionCall(name="or", args=args):
                return any(self._eval(arg, state) for arg in args)

            case FunctionCall(name="not", args=[arg]):
                return not self._eval(arg, state)

            case FunctionCall(name=">", args=[left, right]):
                return self._eval(left, state) > self._eval(right, state)

            case FunctionCall(name="<", args=[left, right]):
                return self._eval(left, state) < self._eval(right, state)

            case FunctionCall(name=">=", args=[left, right]):
                return self._eval(left, state) >= self._eval(right, state)

            case FunctionCall(name="<=", args=[left, right]):
                return self._eval(left, state) <= self._eval(right, state)

            case FunctionCall(name="=", args=[left, right]):
                return self._eval(left, state) == self._eval(right, state)

            case FunctionCall(name="cross-above", args=[a, b]):
                return self._eval_cross_above(a, b, state)

            case FunctionCall(name="cross-below", args=[a, b]):
                return self._eval_cross_below(a, b, state)

            case FunctionCall(name="+", args=args):
                return sum(self._eval(arg, state) for arg in args)

            case FunctionCall(name="-", args=[left, right]):
                return self._eval(left, state) - self._eval(right, state)

            case FunctionCall(name="*", args=args):
                result = 1
                for arg in args:
                    result *= self._eval(arg, state)
                return result

            case FunctionCall(name="/", args=[left, right]):
                divisor = self._eval(right, state)
                if divisor == 0:
                    return float('inf')
                return self._eval(left, state) / divisor

            case FunctionCall(name="prev", args=[expr, n]):
                offset = int(self._eval(n, state))
                return state.get_value_at_offset(self._get_key(expr), offset)

            case FunctionCall(name="has-position", args=[]):
                return state.has_position()

            case FunctionCall(name=name, args=args) if self._is_indicator(name):
                return self._eval_indicator(name, args, state)

            case _:
                raise ValueError(f"Cannot evaluate node: {node}")

    def _eval_cross_above(self, a: ASTNode, b: ASTNode, state: EvaluationState) -> bool:
        """True if a crossed above b (a was below, now above)."""
        a_curr = self._eval(a, state)
        b_curr = self._eval(b, state)
        a_prev = state.get_prev_value(self._get_key(a))
        b_prev = state.get_prev_value(self._get_key(b))

        return a_prev <= b_prev and a_curr > b_curr

    def _eval_cross_below(self, a: ASTNode, b: ASTNode, state: EvaluationState) -> bool:
        """True if a crossed below b."""
        a_curr = self._eval(a, state)
        b_curr = self._eval(b, state)
        a_prev = state.get_prev_value(self._get_key(a))
        b_prev = state.get_prev_value(self._get_key(b))

        return a_prev >= b_prev and a_curr < b_curr

    def _eval_indicator(self, name: str, args: list[ASTNode], state: EvaluationState) -> float:
        """Get pre-computed indicator value from state."""
        # Build indicator key
        source = "close"
        params = []
        output_field = None

        for arg in args:
            if isinstance(arg, Symbol):
                source = arg.name
            elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
                params.append(arg.value)
            elif isinstance(arg, Keyword):
                output_field = arg.name

        key = f"{name}_{source}_{'_'.join(map(str, params))}"
        if output_field:
            key += f"_{output_field}"

        return state.get_indicator(key)

    def _get_key(self, node: ASTNode) -> str:
        """Get the cache key for a node."""
        if isinstance(node, Symbol):
            return node.name
        if isinstance(node, FunctionCall):
            # Simplified key generation
            return f"{node.name}_{'_'.join(str(a) for a in node.args[:3])}"
        return str(node)

    def _is_indicator(self, name: str) -> bool:
        from llamatrade_dsl.validator import INDICATORS
        return name in INDICATORS
```

#### Compiled Strategy

```python
# services/strategy/src/compiler/compiled.py

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
import numpy as np

from llamatrade_dsl.ast import Strategy
from ..strategies.base import Signal, SignalType, Bar
from .extractor import extract_indicators, IndicatorSpec
from .pipeline import IndicatorPipeline
from .evaluator import ConditionEvaluator
from .state import EvaluationState


@dataclass
class Position:
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    entry_time: datetime


class CompiledStrategy:
    """Executable strategy compiled from AST."""

    def __init__(self, ast: Strategy):
        self.name = ast.name
        self.symbols = ast.symbols
        self.timeframe = ast.timeframe
        self.sizing = ast.sizing
        self.risk = ast.risk

        # Extract indicators
        self.indicator_specs = extract_indicators(ast.entry, ast.exit)
        self.pipeline = IndicatorPipeline(self.indicator_specs)

        # Build evaluators
        self.entry_evaluator = ConditionEvaluator(ast.entry)
        self.exit_evaluator = ConditionEvaluator(ast.exit)

        # Calculate warmup
        self.warmup_bars = max(
            (spec.required_bars for spec in self.indicator_specs),
            default=1
        )

    def on_bar(
        self,
        symbol: str,
        bars: list[Bar],
        position: Position | None = None,
    ) -> Signal | None:
        """
        Process a new bar and generate signal if conditions met.

        Args:
            symbol: The symbol being processed
            bars: Historical bars including current (most recent last)
            position: Current position if any

        Returns:
            Signal if entry/exit triggered, None otherwise
        """
        if len(bars) < self.warmup_bars:
            return None

        # Compute indicators
        indicators = self.pipeline.compute(bars)

        # Build evaluation state
        state = EvaluationState(
            current_bar=bars[-1],
            prev_bar=bars[-2] if len(bars) > 1 else bars[-1],
            indicators=indicators,
            position=position,
            bar_history=bars,
        )

        # Check exit first if we have a position
        if position is not None:
            if self.exit_evaluator.evaluate(state):
                return self._make_exit_signal(symbol, bars[-1], position)

        # Check entry if no position
        if position is None:
            if self.entry_evaluator.evaluate(state):
                return self._make_entry_signal(symbol, bars[-1])

        return None

    def _make_entry_signal(self, symbol: str, bar: Bar) -> Signal:
        """Create entry signal with risk parameters."""
        price = bar.close

        stop_loss = None
        take_profit = None

        if self.risk.get("stop_loss_pct"):
            stop_loss = price * (1 - self.risk["stop_loss_pct"] / 100)

        if self.risk.get("take_profit_pct"):
            take_profit = price * (1 + self.risk["take_profit_pct"] / 100)

        return Signal(
            type=SignalType.BUY,
            symbol=symbol,
            price=price,
            timestamp=bar.timestamp,
            quantity_percent=self.sizing.get("value", 10),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def _make_exit_signal(self, symbol: str, bar: Bar, position: Position) -> Signal:
        """Create exit signal."""
        signal_type = (
            SignalType.CLOSE_LONG if position.side == "long"
            else SignalType.CLOSE_SHORT
        )

        return Signal(
            type=signal_type,
            symbol=symbol,
            price=bar.close,
            timestamp=bar.timestamp,
        )


def compile_strategy(ast: Strategy) -> CompiledStrategy:
    """Compile a Strategy AST into executable form."""
    return CompiledStrategy(ast)
```

### 2.4 Phase 2 Deliverables Checklist

| Item | Location | Status |
|------|----------|--------|
| Indicator extractor | `services/strategy/src/compiler/extractor.py` | TODO |
| Indicator pipeline | `services/strategy/src/compiler/pipeline.py` | TODO |
| Evaluation state | `services/strategy/src/compiler/state.py` | TODO |
| Condition evaluator | `services/strategy/src/compiler/evaluator.py` | TODO |
| Signal generator | `services/strategy/src/compiler/signal.py` | TODO |
| CompiledStrategy | `services/strategy/src/compiler/compiled.py` | TODO |
| compile() function | `services/strategy/src/compiler/__init__.py` | TODO |
| Extractor tests | `services/strategy/tests/test_extractor.py` | TODO |
| Evaluator tests | `services/strategy/tests/test_evaluator.py` | TODO |
| Compiler integration tests | `services/strategy/tests/test_compiler.py` | TODO |

---

## Phase 3: Backtest Integration

**Goal:** Wire compiled strategies to BacktestEngine, persist results.

### 3.1 Database Models

**Location:** `libs/db/src/llamatrade_db/models/backtest.py`

```python
# libs/db/src/llamatrade_db/models/backtest.py

from datetime import datetime, date
from enum import Enum as PyEnum
from uuid import UUID, uuid4
from sqlalchemy import (
    Column, String, Text, Integer, Float, Date, DateTime,
    ForeignKey, Enum, Index
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class BacktestStatus(PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Backtest(Base):
    """Backtest job record."""
    __tablename__ = "backtests"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    strategy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[BacktestStatus] = mapped_column(Enum(BacktestStatus), default=BacktestStatus.PENDING)

    # Configuration
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, default=100000)
    commission_rate: Mapped[float] = mapped_column(Float, default=0)
    slippage_rate: Mapped[float] = mapped_column(Float, default=0)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Error info
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationship
    result: Mapped["BacktestResult | None"] = relationship(back_populates="backtest", uselist=False)

    __table_args__ = (
        Index("ix_backtests_tenant_strategy", "tenant_id", "strategy_id"),
        Index("ix_backtests_status", "status"),
    )


class BacktestResult(Base):
    """Backtest results and metrics."""
    __tablename__ = "backtest_results"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    backtest_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("backtests.id"), nullable=False, unique=True)

    # Performance metrics
    total_return: Mapped[float] = mapped_column(Float, nullable=False)
    annual_return: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float)
    sortino_ratio: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_duration_days: Mapped[int | None] = mapped_column(Integer)

    # Trade statistics
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    avg_win: Mapped[float | None] = mapped_column(Float)
    avg_loss: Mapped[float | None] = mapped_column(Float)

    # Final state
    final_equity: Mapped[float] = mapped_column(Float, nullable=False)

    # Detailed data (JSON)
    equity_curve: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)  # [{date, equity}, ...]
    trades: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)  # [{entry_date, exit_date, ...}, ...]
    monthly_returns: Mapped[list[dict] | None] = mapped_column(JSONB)  # [{month, return}, ...]

    # Relationship
    backtest: Mapped["Backtest"] = relationship(back_populates="result")
```

### 3.2 Backtest Service

**Location:** `services/backtest/src/services/backtest_service.py`

```python
# services/backtest/src/services/backtest_service.py

from uuid import UUID
from datetime import date, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from llamatrade_db.models.backtest import Backtest, BacktestResult, BacktestStatus
from llamatrade_db.models.strategy import StrategyVersion
from llamatrade_dsl import parse_strategy
from ..engine.backtester import BacktestEngine, BacktestConfig
from ..compiler import compile_strategy
from ..models import BacktestCreate, BacktestResponse, BacktestResultResponse


class BacktestService:
    def __init__(self, db: AsyncSession, market_data_url: str):
        self.db = db
        self.market_data_url = market_data_url

    async def create_backtest(
        self,
        tenant_id: UUID,
        data: BacktestCreate,
    ) -> BacktestResponse:
        """Create a backtest job (does not run it)."""
        backtest = Backtest(
            tenant_id=tenant_id,
            strategy_id=data.strategy_id,
            version=data.version,
            start_date=data.start_date,
            end_date=data.end_date,
            initial_capital=data.initial_capital or 100000,
            commission_rate=data.commission_rate or 0,
            slippage_rate=data.slippage_rate or 0,
            status=BacktestStatus.PENDING,
        )
        self.db.add(backtest)
        await self.db.commit()

        return self._to_response(backtest)

    async def run_backtest(
        self,
        tenant_id: UUID,
        backtest_id: UUID,
    ) -> BacktestResultResponse:
        """Execute a pending backtest."""
        backtest = await self._get_backtest(tenant_id, backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status != BacktestStatus.PENDING:
            raise ValueError(f"Backtest is {backtest.status.value}, cannot run")

        # Update status
        backtest.status = BacktestStatus.RUNNING
        backtest.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            # Load strategy version
            strategy_version = await self._get_strategy_version(
                tenant_id, backtest.strategy_id, backtest.version
            )
            if not strategy_version:
                raise ValueError("Strategy version not found")

            # Parse and compile
            ast = parse_strategy(strategy_version.config_sexpr)
            compiled = compile_strategy(ast)

            # Fetch historical bars
            bars = await self._fetch_bars(
                symbols=compiled.symbols,
                timeframe=compiled.timeframe,
                start_date=backtest.start_date,
                end_date=backtest.end_date,
            )

            # Run backtest
            engine = BacktestEngine(BacktestConfig(
                initial_capital=backtest.initial_capital,
                commission_rate=backtest.commission_rate,
                slippage_rate=backtest.slippage_rate,
            ))

            result = engine.run(
                bar_data=bars,
                strategy_fn=compiled.on_bar,
                start_date=backtest.start_date,
                end_date=backtest.end_date,
            )

            # Save result
            backtest_result = BacktestResult(
                backtest_id=backtest.id,
                total_return=result.total_return,
                annual_return=result.annual_return,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                max_drawdown=result.max_drawdown,
                max_drawdown_duration_days=result.max_drawdown_duration_days,
                total_trades=result.total_trades,
                winning_trades=result.winning_trades,
                losing_trades=result.losing_trades,
                win_rate=result.win_rate,
                profit_factor=result.profit_factor,
                avg_win=result.avg_win,
                avg_loss=result.avg_loss,
                final_equity=result.final_equity,
                equity_curve=result.equity_curve,
                trades=result.trades,
                monthly_returns=result.monthly_returns,
            )
            self.db.add(backtest_result)

            backtest.status = BacktestStatus.COMPLETED
            backtest.completed_at = datetime.utcnow()
            await self.db.commit()

            return self._to_result_response(backtest, backtest_result)

        except Exception as e:
            backtest.status = BacktestStatus.FAILED
            backtest.error_message = str(e)
            backtest.completed_at = datetime.utcnow()
            await self.db.commit()
            raise

    async def get_backtest(
        self,
        tenant_id: UUID,
        backtest_id: UUID,
    ) -> BacktestResponse | None:
        """Get backtest by ID."""
        backtest = await self._get_backtest(tenant_id, backtest_id)
        return self._to_response(backtest) if backtest else None

    async def get_result(
        self,
        tenant_id: UUID,
        backtest_id: UUID,
    ) -> BacktestResultResponse | None:
        """Get backtest result."""
        backtest = await self._get_backtest(tenant_id, backtest_id)
        if not backtest or not backtest.result:
            return None
        return self._to_result_response(backtest, backtest.result)

    async def list_backtests(
        self,
        tenant_id: UUID,
        strategy_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BacktestResponse], int]:
        """List backtests with pagination."""
        stmt = select(Backtest).where(Backtest.tenant_id == tenant_id)

        if strategy_id:
            stmt = stmt.where(Backtest.strategy_id == strategy_id)

        stmt = stmt.order_by(Backtest.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        backtests = result.scalars().all()

        # TODO: count query
        total = len(backtests)

        return [self._to_response(b) for b in backtests], total

    # --- Private helpers ---

    async def _get_backtest(self, tenant_id: UUID, backtest_id: UUID) -> Backtest | None:
        stmt = (
            select(Backtest)
            .where(Backtest.id == backtest_id)
            .where(Backtest.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_strategy_version(
        self, tenant_id: UUID, strategy_id: UUID, version: int
    ) -> StrategyVersion | None:
        # Query strategy version (with tenant check via strategy)
        stmt = (
            select(StrategyVersion)
            .join(Strategy)
            .where(Strategy.tenant_id == tenant_id)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, list]:
        """Fetch historical bars from market-data service."""
        async with httpx.AsyncClient() as client:
            bars = {}
            for symbol in symbols:
                response = await client.get(
                    f"{self.market_data_url}/bars/{symbol}",
                    params={
                        "timeframe": timeframe,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    }
                )
                response.raise_for_status()
                bars[symbol] = response.json()["bars"]
            return bars

    def _to_response(self, b: Backtest) -> BacktestResponse:
        return BacktestResponse(
            id=b.id,
            strategy_id=b.strategy_id,
            version=b.version,
            status=b.status.value,
            start_date=b.start_date,
            end_date=b.end_date,
            initial_capital=b.initial_capital,
            created_at=b.created_at,
            completed_at=b.completed_at,
            error_message=b.error_message,
        )

    def _to_result_response(self, b: Backtest, r: BacktestResult) -> BacktestResultResponse:
        return BacktestResultResponse(
            backtest_id=b.id,
            total_return=r.total_return,
            annual_return=r.annual_return,
            sharpe_ratio=r.sharpe_ratio,
            sortino_ratio=r.sortino_ratio,
            max_drawdown=r.max_drawdown,
            total_trades=r.total_trades,
            win_rate=r.win_rate,
            profit_factor=r.profit_factor,
            final_equity=r.final_equity,
            equity_curve=r.equity_curve,
            trades=r.trades,
        )
```

### 3.3 Phase 3 Deliverables Checklist

| Item | Location | Status |
|------|----------|--------|
| Backtest model | `libs/db/src/llamatrade_db/models/backtest.py` | TODO |
| BacktestResult model | `libs/db/src/llamatrade_db/models/backtest.py` | TODO |
| Alembic migration | `libs/db/migrations/versions/xxx_add_backtest_tables.py` | TODO |
| Backtest service | `services/backtest/src/services/backtest_service.py` | TODO |
| Market data client | `services/backtest/src/clients/market_data.py` | TODO |
| Backtest router update | `services/backtest/src/routers/backtests.py` | TODO |
| Pydantic schemas | `services/backtest/src/models.py` | TODO |
| Service integration tests | `services/backtest/tests/test_backtest_service.py` | TODO |
| End-to-end tests | `services/backtest/tests/test_e2e.py` | TODO |

---

## Phase 4: Live Trading Pipeline

**Goal:** Execute strategies in real-time via Alpaca.

### 4.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LIVE TRADING SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐    ┌─────────────────────────────────────────────┐   │
│   │ Deployment  │    │              Strategy Runner                 │   │
│   │   Service   │───▶│                                             │   │
│   │             │    │  ┌─────────┐  ┌──────────┐  ┌───────────┐  │   │
│   │ start/stop  │    │  │  Bar    │  │ Compiled │  │  Signal   │  │   │
│   │ pause       │    │  │ Stream  │─▶│ Strategy │─▶│ Generator │  │   │
│   └─────────────┘    │  └─────────┘  └──────────┘  └─────┬─────┘  │   │
│                      │                                    │        │   │
│                      │                              ┌─────▼─────┐  │   │
│                      │                              │   Risk    │  │   │
│                      │                              │  Manager  │  │   │
│                      │                              └─────┬─────┘  │   │
│                      │                                    │        │   │
│                      │                              ┌─────▼─────┐  │   │
│                      │                              │   Order   │  │   │
│                      │                              │  Manager  │  │   │
│                      │                              └─────┬─────┘  │   │
│                      └────────────────────────────────────┼────────┘   │
│                                                           │            │
│   ┌─────────────────────────────────────────────────────▼─────────┐   │
│   │                      Order Executor                            │   │
│   │                                                                │   │
│   │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │   │
│   │   │ Alpaca REST  │    │ Bracket      │    │  Position    │    │   │
│   │   │ Client       │    │ Orders       │    │  Tracker     │    │   │
│   │   └──────────────┘    └──────────────┘    └──────────────┘    │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                      │                                  │
└──────────────────────────────────────┼──────────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   Alpaca API    │
                              │  (Paper/Live)   │
                              └─────────────────┘
```

### 4.2 File Structure

**Location:** `services/trading/src/`

```
services/trading/src/
├── main.py
├── models.py
├── routers/
│   ├── deployments.py      # Deployment management API
│   ├── orders.py           # Order history API
│   └── positions.py        # Position queries API
├── services/
│   ├── deployment_service.py
│   ├── order_service.py
│   └── position_service.py
├── runner/
│   ├── __init__.py
│   ├── runner.py           # StrategyRunner class
│   ├── bar_stream.py       # Alpaca websocket streaming
│   ├── order_manager.py    # Signal → Order conversion
│   └── position_tracker.py # Track open positions
├── executor/
│   ├── __init__.py
│   ├── alpaca_client.py    # Alpaca API wrapper
│   └── order_executor.py   # Execute orders
└── risk/
    ├── __init__.py
    └── risk_manager.py     # Pre-trade risk checks
```

### 4.3 Core Components

#### Strategy Runner

```python
# services/trading/src/runner/runner.py

import asyncio
from uuid import UUID
from datetime import datetime
from typing import AsyncGenerator

from llamatrade_db.models.strategy import StrategyDeployment, DeploymentStatus
from llamatrade_dsl import parse_strategy
from ...compiler import compile_strategy, CompiledStrategy
from ..strategies.base import Bar, Signal
from .bar_stream import AlpacaBarStream
from .order_manager import OrderManager
from .position_tracker import PositionTracker
from ..executor import OrderExecutor
from ..risk import RiskManager


class StrategyRunner:
    """Runs a compiled strategy in real-time."""

    def __init__(
        self,
        deployment: StrategyDeployment,
        compiled: CompiledStrategy,
        bar_stream: AlpacaBarStream,
        order_manager: OrderManager,
        executor: OrderExecutor,
        risk_manager: RiskManager,
        position_tracker: PositionTracker,
    ):
        self.deployment = deployment
        self.compiled = compiled
        self.bar_stream = bar_stream
        self.order_manager = order_manager
        self.executor = executor
        self.risk_manager = risk_manager
        self.position_tracker = position_tracker

        self._running = False
        self._bar_history: dict[str, list[Bar]] = {
            s: [] for s in compiled.symbols
        }

    async def start(self):
        """Start the strategy runner."""
        self._running = True

        # Subscribe to bar stream
        await self.bar_stream.subscribe(
            self.compiled.symbols,
            self.compiled.timeframe,
        )

        # Main loop
        async for bar in self.bar_stream.stream():
            if not self._running:
                break

            await self._process_bar(bar)

    async def stop(self):
        """Stop the strategy runner gracefully."""
        self._running = False
        await self.bar_stream.unsubscribe()

    async def _process_bar(self, bar: Bar):
        """Process incoming bar data."""
        symbol = bar.symbol

        # Add to history
        self._bar_history[symbol].append(bar)

        # Limit history size
        max_history = self.compiled.warmup_bars + 100
        if len(self._bar_history[symbol]) > max_history:
            self._bar_history[symbol] = self._bar_history[symbol][-max_history:]

        # Skip if warming up
        if len(self._bar_history[symbol]) < self.compiled.warmup_bars:
            return

        # Get current position
        position = await self.position_tracker.get_position(symbol)

        # Generate signal
        signal = self.compiled.on_bar(
            symbol=symbol,
            bars=self._bar_history[symbol],
            position=position,
        )

        if signal:
            await self._process_signal(signal)

    async def _process_signal(self, signal: Signal):
        """Process generated signal through risk and execution."""
        # Risk check
        risk_result = await self.risk_manager.check(signal, self.deployment)
        if not risk_result.approved:
            await self._log_risk_rejection(signal, risk_result)
            return

        # Convert to order
        order = await self.order_manager.create_order(signal)
        if not order:
            return

        # Execute
        result = await self.executor.execute(order)

        # Update position tracker
        if result.filled:
            await self.position_tracker.update(signal.symbol, result)

        # Log execution
        await self._log_execution(signal, order, result)
```

#### Alpaca Order Executor

```python
# services/trading/src/executor/order_executor.py

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest,
    StopOrderRequest, StopLimitOrderRequest,
    TakeProfitRequest, StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType


@dataclass
class Order:
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    order_type: Literal["market", "limit"]
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    time_in_force: str = "day"


@dataclass
class OrderResult:
    order_id: str
    status: str
    filled: bool
    filled_qty: float
    filled_price: float | None
    submitted_at: datetime
    error: str | None = None


class OrderExecutor:
    """Execute orders via Alpaca API."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )

    async def execute(self, order: Order) -> OrderResult:
        """Submit order to Alpaca."""
        try:
            # Build order request
            side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY

            if order.order_type == "market":
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=side,
                    time_in_force=tif,
                )
            else:
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=side,
                    time_in_force=tif,
                    limit_price=order.limit_price,
                )

            # Submit main order
            alpaca_order = self.client.submit_order(request)

            # Submit bracket orders if needed
            if order.stop_loss or order.take_profit:
                await self._submit_bracket_orders(
                    alpaca_order.id,
                    order.symbol,
                    order.quantity,
                    side,
                    order.stop_loss,
                    order.take_profit,
                )

            return OrderResult(
                order_id=str(alpaca_order.id),
                status=alpaca_order.status.value,
                filled=alpaca_order.status.value == "filled",
                filled_qty=float(alpaca_order.filled_qty or 0),
                filled_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
                submitted_at=alpaca_order.submitted_at,
            )

        except Exception as e:
            return OrderResult(
                order_id="",
                status="error",
                filled=False,
                filled_qty=0,
                filled_price=None,
                submitted_at=datetime.utcnow(),
                error=str(e),
            )

    async def _submit_bracket_orders(
        self,
        parent_order_id: str,
        symbol: str,
        quantity: float,
        entry_side: OrderSide,
        stop_loss: float | None,
        take_profit: float | None,
    ):
        """Submit stop-loss and take-profit orders."""
        exit_side = OrderSide.SELL if entry_side == OrderSide.BUY else OrderSide.BUY

        if stop_loss:
            sl_request = StopOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=exit_side,
                stop_price=stop_loss,
                time_in_force=TimeInForce.GTC,
            )
            self.client.submit_order(sl_request)

        if take_profit:
            tp_request = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=exit_side,
                limit_price=take_profit,
                time_in_force=TimeInForce.GTC,
            )
            self.client.submit_order(tp_request)
```

### 4.4 Database Models

```python
# libs/db/src/llamatrade_db/models/execution.py

class ExecutionLog(Base):
    """Log of all signals and order executions."""
    __tablename__ = "execution_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    deployment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("strategy_deployments.id"))

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # signal, order, fill, risk_reject

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_type: Mapped[str | None] = mapped_column(String(20))

    order_id: Mapped[str | None] = mapped_column(String(100))
    order_side: Mapped[str | None] = mapped_column(String(10))
    order_quantity: Mapped[float | None] = mapped_column(Float)
    order_price: Mapped[float | None] = mapped_column(Float)

    filled_quantity: Mapped[float | None] = mapped_column(Float)
    filled_price: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    metadata: Mapped[dict | None] = mapped_column(JSONB)


class LivePosition(Base):
    """Current live positions from deployments."""
    __tablename__ = "live_positions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    deployment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("strategy_deployments.id"))

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # long, short
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    current_price: Mapped[float] = mapped_column(Float)
    unrealized_pnl: Mapped[float] = mapped_column(Float)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float)

    stop_loss: Mapped[float | None] = mapped_column(Float)
    take_profit: Mapped[float | None] = mapped_column(Float)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_live_positions_deployment", "deployment_id"),
        UniqueConstraint("deployment_id", "symbol", name="uq_deployment_symbol"),
    )
```

### 4.5 Phase 4 Deliverables Checklist

| Item | Location | Status |
|------|----------|--------|
| ExecutionLog model | `libs/db/src/llamatrade_db/models/execution.py` | TODO |
| LivePosition model | `libs/db/src/llamatrade_db/models/execution.py` | TODO |
| Alembic migration | `libs/db/migrations/versions/xxx_add_execution_tables.py` | TODO |
| Alpaca bar stream | `services/trading/src/runner/bar_stream.py` | TODO |
| Strategy runner | `services/trading/src/runner/runner.py` | TODO |
| Order manager | `services/trading/src/runner/order_manager.py` | TODO |
| Position tracker | `services/trading/src/runner/position_tracker.py` | TODO |
| Order executor | `services/trading/src/executor/order_executor.py` | TODO |
| Alpaca client wrapper | `services/trading/src/executor/alpaca_client.py` | TODO |
| Deployment service | `services/trading/src/services/deployment_service.py` | TODO |
| Deployment router | `services/trading/src/routers/deployments.py` | TODO |
| Risk manager | `services/trading/src/risk/risk_manager.py` | TODO |
| Integration tests | `services/trading/tests/test_runner.py` | TODO |
| Paper trading e2e | `services/trading/tests/test_paper_trading.py` | TODO |

---

## Phase 5: Monitoring & Risk

**Goal:** Production-grade guardrails and observability.

### 5.1 Risk Manager

```python
# services/trading/src/risk/risk_manager.py

from dataclasses import dataclass
from uuid import UUID
from datetime import datetime, timedelta

from llamatrade_db.models.strategy import StrategyDeployment
from ..strategies.base import Signal


@dataclass
class RiskCheckResult:
    approved: bool
    checks_passed: list[str]
    checks_failed: list[str]
    reason: str | None = None


class RiskManager:
    """Pre-trade risk validation."""

    def __init__(self, db, position_tracker, account_service):
        self.db = db
        self.position_tracker = position_tracker
        self.account_service = account_service

    async def check(
        self,
        signal: Signal,
        deployment: StrategyDeployment,
    ) -> RiskCheckResult:
        """Run all risk checks on a signal."""
        passed = []
        failed = []

        # Get risk config
        config = deployment.config_override or {}
        risk = config.get("risk", {})

        # 1. Position size limit
        if await self._check_position_size(signal, risk):
            passed.append("position_size")
        else:
            failed.append("position_size")

        # 2. Max positions
        if await self._check_max_positions(deployment, risk):
            passed.append("max_positions")
        else:
            failed.append("max_positions")

        # 3. Daily loss limit
        if await self._check_daily_loss(deployment, risk):
            passed.append("daily_loss")
        else:
            failed.append("daily_loss")

        # 4. Drawdown limit
        if await self._check_drawdown(deployment, risk):
            passed.append("drawdown")
        else:
            failed.append("drawdown")

        # 5. Order rate limit
        if await self._check_rate_limit(deployment):
            passed.append("rate_limit")
        else:
            failed.append("rate_limit")

        approved = len(failed) == 0
        reason = f"Failed checks: {', '.join(failed)}" if failed else None

        return RiskCheckResult(
            approved=approved,
            checks_passed=passed,
            checks_failed=failed,
            reason=reason,
        )

    async def _check_position_size(self, signal: Signal, risk: dict) -> bool:
        """Check position doesn't exceed max size."""
        max_pct = risk.get("max_position_size_pct", 10)
        return signal.quantity_percent <= max_pct

    async def _check_max_positions(self, deployment: StrategyDeployment, risk: dict) -> bool:
        """Check we haven't exceeded max open positions."""
        max_positions = risk.get("max_positions", 10)
        current = await self.position_tracker.count_positions(deployment.id)
        return current < max_positions

    async def _check_daily_loss(self, deployment: StrategyDeployment, risk: dict) -> bool:
        """Check daily loss limit not exceeded."""
        max_loss_pct = risk.get("max_daily_loss_pct")
        if not max_loss_pct:
            return True

        daily_pnl = await self._get_daily_pnl(deployment.id)
        account = await self.account_service.get_account(deployment.tenant_id)

        loss_pct = (daily_pnl / account.equity) * 100
        return loss_pct > -max_loss_pct

    async def _check_drawdown(self, deployment: StrategyDeployment, risk: dict) -> bool:
        """Check drawdown limit not exceeded."""
        max_dd_pct = risk.get("max_drawdown_pct")
        if not max_dd_pct:
            return True

        current_dd = await self._get_current_drawdown(deployment.id)
        return current_dd < max_dd_pct

    async def _check_rate_limit(self, deployment: StrategyDeployment) -> bool:
        """Check order rate limit not exceeded."""
        # Max 10 orders per minute
        max_per_minute = 10
        recent_orders = await self._count_recent_orders(deployment.id, minutes=1)
        return recent_orders < max_per_minute
```

### 5.2 Audit Trail

```python
# services/trading/src/services/audit_service.py

from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.audit import AuditLog


class AuditService:
    """Record all trading events for compliance and debugging."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_signal(
        self,
        tenant_id: UUID,
        deployment_id: UUID,
        signal: Signal,
    ):
        """Log signal generation."""
        await self._log(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            event_type="signal",
            data={
                "signal_type": signal.type.value,
                "symbol": signal.symbol,
                "price": signal.price,
                "quantity_percent": signal.quantity_percent,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
            }
        )

    async def log_order(
        self,
        tenant_id: UUID,
        deployment_id: UUID,
        order: Order,
        result: OrderResult,
    ):
        """Log order submission and result."""
        await self._log(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            event_type="order",
            data={
                "order_id": result.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "status": result.status,
                "filled_qty": result.filled_qty,
                "filled_price": result.filled_price,
                "error": result.error,
            }
        )

    async def log_risk_rejection(
        self,
        tenant_id: UUID,
        deployment_id: UUID,
        signal: Signal,
        result: RiskCheckResult,
    ):
        """Log risk check rejection."""
        await self._log(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            event_type="risk_rejection",
            data={
                "signal_type": signal.type.value,
                "symbol": signal.symbol,
                "checks_failed": result.checks_failed,
                "reason": result.reason,
            }
        )

    async def _log(
        self,
        tenant_id: UUID,
        deployment_id: UUID,
        event_type: str,
        data: dict,
    ):
        log = AuditLog(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            data=data,
        )
        self.db.add(log)
        await self.db.commit()
```

### 5.3 Alert Service

```python
# services/notification/src/services/alert_service.py

from enum import Enum
from dataclasses import dataclass
from uuid import UUID

class AlertPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(Enum):
    ORDER_FILLED = "order_filled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    RISK_BREACH = "risk_breach"
    STRATEGY_ERROR = "strategy_error"
    DEPLOYMENT_STARTED = "deployment_started"
    DEPLOYMENT_STOPPED = "deployment_stopped"

@dataclass
class Alert:
    tenant_id: UUID
    deployment_id: UUID | None
    alert_type: AlertType
    priority: AlertPriority
    title: str
    message: str
    metadata: dict | None = None


class AlertService:
    """Send notifications for important trading events."""

    def __init__(self, webhook_service, email_service):
        self.webhook_service = webhook_service
        self.email_service = email_service

    async def send(self, alert: Alert):
        """Send alert via configured channels."""
        # Get user notification preferences
        prefs = await self._get_preferences(alert.tenant_id)

        # Send via webhook if configured
        if prefs.webhook_url:
            await self.webhook_service.send(
                url=prefs.webhook_url,
                payload=self._to_webhook_payload(alert),
            )

        # Send email for high priority
        if alert.priority in (AlertPriority.HIGH, AlertPriority.CRITICAL):
            if prefs.email:
                await self.email_service.send(
                    to=prefs.email,
                    subject=f"[{alert.priority.value.upper()}] {alert.title}",
                    body=alert.message,
                )

    async def on_order_filled(self, tenant_id: UUID, deployment_id: UUID, order, result):
        await self.send(Alert(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title=f"Order Filled: {order.side.upper()} {order.symbol}",
            message=f"Filled {result.filled_qty} @ ${result.filled_price:.2f}",
            metadata={"order_id": result.order_id},
        ))

    async def on_risk_breach(self, tenant_id: UUID, deployment_id: UUID, check_result):
        await self.send(Alert(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            alert_type=AlertType.RISK_BREACH,
            priority=AlertPriority.HIGH,
            title="Risk Limit Breached",
            message=f"Failed checks: {', '.join(check_result.checks_failed)}",
        ))

    async def on_strategy_error(self, tenant_id: UUID, deployment_id: UUID, error: Exception):
        await self.send(Alert(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            alert_type=AlertType.STRATEGY_ERROR,
            priority=AlertPriority.CRITICAL,
            title="Strategy Error",
            message=str(error),
        ))
```

### 5.4 Phase 5 Deliverables Checklist

| Item | Location | Status |
|------|----------|--------|
| AuditLog model | `libs/db/src/llamatrade_db/models/audit.py` | TODO |
| Alembic migration | `libs/db/migrations/versions/xxx_add_audit_tables.py` | TODO |
| Risk manager | `services/trading/src/risk/risk_manager.py` | TODO |
| Audit service | `services/trading/src/services/audit_service.py` | TODO |
| Alert service | `services/notification/src/services/alert_service.py` | TODO |
| Webhook sender | `services/notification/src/services/webhook_service.py` | TODO |
| Metrics exporter | `services/trading/src/metrics.py` | TODO |
| Risk config schema | `services/trading/src/models.py` | TODO |
| Unit tests | `services/trading/tests/test_risk_manager.py` | TODO |

---

## Implementation Order

Recommended order for implementation:

```
Week 1-2: Phase 1 (DSL & Data Model)
├── Day 1-2: AST nodes and parser
├── Day 3-4: Validator and serializer
├── Day 5-6: SQLAlchemy models + migration
├── Day 7-8: Strategy service CRUD
└── Day 9-10: Tests

Week 3-4: Phase 2 (Compiler)
├── Day 1-2: Indicator extractor
├── Day 3-4: Indicator pipeline (connect to existing indicators)
├── Day 5-6: Condition evaluator
├── Day 7-8: CompiledStrategy class
└── Day 9-10: Tests

Week 5-6: Phase 3 (Backtest Integration)
├── Day 1-2: Backtest models + migration
├── Day 3-4: Backtest service
├── Day 5-6: Wire to existing BacktestEngine
├── Day 7-8: API endpoints
└── Day 9-10: E2E tests

Week 7-8: Phase 4 (Live Trading)
├── Day 1-3: Alpaca client + bar stream
├── Day 4-5: Strategy runner
├── Day 6-7: Order executor
├── Day 8-9: Deployment service
└── Day 10: Paper trading tests

Week 9-10: Phase 5 (Monitoring)
├── Day 1-2: Risk manager
├── Day 3-4: Audit service
├── Day 5-6: Alert service
├── Day 7-8: Metrics
└── Day 9-10: Integration tests
```

---

## Testing Strategy

### Unit Tests

Every component should have unit tests:
- Parser: valid/invalid inputs, edge cases
- Validator: all error conditions
- Evaluator: all operators, cross detection
- Risk manager: each check type

### Integration Tests

- Strategy creation → versioning → retrieval
- Parse → compile → backtest flow
- Signal → risk check → order execution

### E2E Tests

- Create strategy via API → run backtest → verify results
- Deploy to paper → verify signals → verify orders

### Test Coverage Targets

| Component | Target |
|-----------|--------|
| libs/dsl | 90% |
| Strategy service | 85% |
| Compiler | 85% |
| Backtest service | 80% |
| Trading runner | 75% |
| Risk manager | 90% |

---

## Dependencies Summary

### New Libraries

```toml
# libs/dsl/pyproject.toml
[project]
name = "llamatrade-dsl"
dependencies = []  # Pure Python, no external deps

# services/trading additions
alpaca-py = "^0.21"
websockets = "^12.0"
```

### Service Dependencies

```
strategy service → libs/dsl, libs/db
backtest service → libs/dsl, strategy service, market-data service
trading service  → libs/dsl, strategy service, market-data service, alpaca
notification     → (standalone)
```

---

## Open Questions

1. **Strategy cloning across tenants?** - Should templates be system-wide or per-tenant?
2. **Backtest job queue?** - Use Celery or simple async? (Recommend Celery for long backtests)
3. **Live position sync?** - How often to sync with Alpaca positions? (Recommend: on startup + every fill)
4. **Multi-symbol strategies?** - Should one signal affect all symbols or per-symbol? (Recommend: per-symbol)

---

*Plan created: 2024*
*Last updated: 2024*
