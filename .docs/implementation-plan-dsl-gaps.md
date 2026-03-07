# DSL System Implementation Plan

This plan addresses the 94 gaps identified across the DSL system, organized into phases with clear priorities, dependencies, and acceptance criteria.

---

## Executive Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| DSL Parser | 3 | 5 | 5 | 2 | 15 |
| Compiler | 4 | 6 | 3 | 2 | 15 |
| Frontend | 6 | 8 | 10 | 4 | 28 |
| Service/DB | 8 | 6 | 7 | 3 | 24 |
| Execution | 3 | 4 | 3 | 2 | 12 |
| **Total** | **24** | **29** | **28** | **13** | **94** |

**Recommended Timeline:** 8-10 weeks for critical + high priority items

---

## Phase 1: Critical Fixes (Week 1-2)

### 1.1 Parser Source Location Tracking
**Priority:** Critical | **Effort:** 2 days | **Risk:** Low

**Problem:** Parser doesn't track source locations, making error messages unhelpful.

**Files to modify:**
- `libs/dsl/llamatrade_dsl/parser.py`
- `libs/dsl/llamatrade_dsl/ast.py`

**Implementation:**
```python
# ast.py - Add SourceLocation to all nodes
@dataclass
class SourceLocation:
    line: int
    column: int
    start_offset: int
    end_offset: int

@dataclass
class ASTNode:
    location: SourceLocation | None = None

# parser.py - Track position during tokenization
class Tokenizer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1

    def _advance(self) -> str:
        char = self.source[self.pos]
        self.pos += 1
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char
```

**Acceptance Criteria:**
- [ ] All AST nodes have optional `location` field
- [ ] Parser populates location for all nodes
- [ ] Error messages include line:column
- [ ] Unit tests verify location accuracy

---

### 1.2 Indicator Registry Synchronization
**Priority:** Critical | **Effort:** 1 day | **Risk:** Low

**Problem:** Compiler supports 17 indicators but validator only knows 11.

**Files to modify:**
- `libs/dsl/llamatrade_dsl/validator.py`
- `libs/compiler/llamatrade_compiler/extractor.py`

**Implementation:**
```python
# Create single source of truth in libs/dsl
SUPPORTED_INDICATORS = {
    # Trend
    'sma': {'params': ['source', 'period'], 'default_period': 20},
    'ema': {'params': ['source', 'period'], 'default_period': 20},
    'wma': {'params': ['source', 'period'], 'default_period': 20},
    'dema': {'params': ['source', 'period'], 'default_period': 20},
    'tema': {'params': ['source', 'period'], 'default_period': 20},
    'kama': {'params': ['source', 'period'], 'default_period': 10},

    # Momentum
    'rsi': {'params': ['source', 'period'], 'default_period': 14},
    'stoch-k': {'params': ['period'], 'default_period': 14},
    'stoch-d': {'params': ['period', 'smooth'], 'default_period': 14},
    'cci': {'params': ['period'], 'default_period': 20},
    'williams-r': {'params': ['period'], 'default_period': 14},
    'roc': {'params': ['source', 'period'], 'default_period': 10},
    'momentum': {'params': ['source', 'period'], 'default_period': 10},

    # Volatility
    'atr': {'params': ['period'], 'default_period': 14},
    'bb-upper': {'params': ['source', 'period', 'std'], 'default_period': 20},
    'bb-lower': {'params': ['source', 'period', 'std'], 'default_period': 20},
    'bb-middle': {'params': ['source', 'period'], 'default_period': 20},

    # Volume
    'obv': {'params': []},
    'vwap': {'params': []},
    'ad': {'params': []},  # Accumulation/Distribution
    'adx': {'params': ['period'], 'default_period': 14},

    # MACD family
    'macd-line': {'params': ['fast', 'slow'], 'defaults': [12, 26]},
    'macd-signal': {'params': ['fast', 'slow', 'signal'], 'defaults': [12, 26, 9]},
    'macd-hist': {'params': ['fast', 'slow', 'signal'], 'defaults': [12, 26, 9]},
}

# Compiler imports from validator
from llamatrade_dsl.validator import SUPPORTED_INDICATORS
```

**Acceptance Criteria:**
- [ ] Single `SUPPORTED_INDICATORS` dict in `libs/dsl`
- [ ] Compiler imports from DSL lib
- [ ] All 17+ indicators in registry with param specs
- [ ] Validator uses same registry for validation

---

### 1.3 Frontend fromDSL() Round-Trip
**Priority:** Critical | **Effort:** 3 days | **Risk:** Medium

**Problem:** `fromDSL()` cannot fully reconstruct block tree from DSL string.

**Files to modify:**
- `apps/web/src/services/strategy-serializer.ts`

**Implementation:**
The linter already added a partial implementation. Complete it:

```typescript
// Complete the fromDSLString implementation
export function fromDSLString(dsl: string): { tree: StrategyTree; metadata: StrategyMetadata } {
  const tokens = tokenizeWithPositions(dsl);
  const parser = new DSLParser(tokens);
  return parser.parse();
}

class DSLParser {
  private pos = 0;
  private blockIdCounter = 0;

  parse(): { tree: StrategyTree; metadata: StrategyMetadata } {
    const blocks: Record<string, Block> = {};
    const rootId = this.generateId();

    // Parse (strategy "name" :rebalance freq ...)
    this.expect('(');
    this.expectKeyword('strategy');
    const name = this.parseString();

    // Parse optional parameters
    let rebalance = 'daily';
    let description = '';

    while (this.peek()?.type === 'parameter') {
      const param = this.advance();
      if (param.value === ':rebalance') {
        rebalance = this.advance().value;
      } else if (param.value === ':description') {
        description = this.parseString();
      }
    }

    // Parse children (weight, group, if, filter blocks)
    const childIds: string[] = [];
    while (!this.check(')')) {
      const childId = this.parseBlock(blocks);
      childIds.push(childId);
    }

    this.expect(')');

    // Create root block
    blocks[rootId] = {
      id: rootId,
      type: 'root',
      childIds,
    };

    return {
      tree: { blocks, rootId },
      metadata: {
        name,
        description,
        timeframe: rebalanceToTimeframe(rebalance),
        type: 'allocation',
      },
    };
  }

  private parseBlock(blocks: Record<string, Block>): string {
    this.expect('(');
    const keyword = this.advance().value;

    switch (keyword) {
      case 'weight': return this.parseWeightBlock(blocks);
      case 'asset': return this.parseAssetBlock(blocks);
      case 'group': return this.parseGroupBlock(blocks);
      case 'if': return this.parseIfBlock(blocks);
      case 'filter': return this.parseFilterBlock(blocks);
      default: throw new Error(`Unknown block type: ${keyword}`);
    }
  }

  // ... implement each parse method
}
```

**Acceptance Criteria:**
- [ ] `fromDSLString()` parses all valid DSL constructs
- [ ] Round-trip: `fromDSLString(toDSL(tree))` equals original tree
- [ ] Proper error messages with line/column on parse failure
- [ ] Handles all block types: weight, asset, group, if, filter
- [ ] Unit tests for each construct type

---

### 1.4 Transaction Safety in Strategy Service
**Priority:** Critical | **Effort:** 2 days | **Risk:** High

**Problem:** `create_strategy` + `create_version` not atomic; partial failures possible.

**Files to modify:**
- `services/strategy/src/services/strategy_service.py`

**Implementation:**
```python
async def create_strategy(
    self,
    tenant_id: str,
    name: str,
    dsl_source: str,
    description: str | None = None,
    parameters: dict | None = None,
) -> Strategy:
    """Create strategy with initial version atomically."""
    async with self.db.begin() as session:  # Transaction context
        # Validate DSL first (before any DB operations)
        try:
            ast = parse_dsl(dsl_source)
            validate_ast(ast)
        except DSLError as e:
            raise InvalidStrategyError(str(e)) from e

        # Create strategy record
        strategy = Strategy(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(strategy)

        # Create initial version (v1)
        version = StrategyVersion(
            id=str(uuid4()),
            strategy_id=strategy.id,
            version=1,
            dsl_source=dsl_source,
            parameters=parameters or {},
            created_at=datetime.utcnow(),
        )
        session.add(version)

        # Both committed together or both rolled back
        await session.commit()

    return strategy
```

**Acceptance Criteria:**
- [ ] All create/update operations use transaction context
- [ ] Partial failures roll back completely
- [ ] Integration test verifies atomicity
- [ ] No orphaned strategies without versions

---

### 1.5 Tenant Isolation Enforcement
**Priority:** Critical | **Effort:** 2 days | **Risk:** High

**Problem:** Some queries may not filter by tenant_id consistently.

**Files to modify:**
- `services/strategy/src/services/strategy_service.py`
- `services/backtest/src/services/backtest_service.py`
- `services/trading/src/services/session_service.py`

**Implementation:**
```python
# Add tenant_id to ALL queries - use SQLAlchemy event to enforce

from sqlalchemy import event
from sqlalchemy.orm import Query

@event.listens_for(Query, "before_compile", retval=True)
def ensure_tenant_filter(query):
    """Automatically add tenant_id filter to all queries."""
    # Get tenant_id from context
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise SecurityError("No tenant context - query rejected")

    # Add tenant filter to all mapped classes that have tenant_id
    for desc in query.column_descriptions:
        entity = desc.get('entity')
        if entity and hasattr(entity, 'tenant_id'):
            query = query.filter(entity.tenant_id == tenant_id)

    return query

# Explicit pattern for services
class StrategyService:
    async def get_strategy(self, tenant_id: str, strategy_id: str) -> Strategy | None:
        # ALWAYS filter by tenant_id first
        return await self.db.scalar(
            select(Strategy)
            .where(Strategy.tenant_id == tenant_id)  # First condition
            .where(Strategy.id == strategy_id)
        )
```

**Acceptance Criteria:**
- [ ] All queries include tenant_id filter
- [ ] Integration tests verify cross-tenant isolation
- [ ] Audit log captures any isolation violations
- [ ] SQLAlchemy event hook as safety net

---

### 1.6 Rebalancing Logic Implementation
**Priority:** Critical | **Effort:** 3 days | **Risk:** High

**Problem:** Strategy execution ignores rebalance frequency entirely.

**Files to modify:**
- `services/backtest/src/engine/strategy_adapter.py`
- `services/trading/src/compiler_adapter.py`
- `services/trading/src/runner/runner.py`

**Implementation:**
```python
# strategy_adapter.py
class CompiledStrategyAdapter:
    def __init__(self, compiled: CompiledStrategy):
        self.compiled = compiled
        self.rebalance_freq = compiled.rebalance_frequency
        self.last_rebalance: date | None = None

    def should_rebalance(self, current_date: date) -> bool:
        """Check if rebalancing is due based on frequency."""
        if self.last_rebalance is None:
            return True

        match self.rebalance_freq:
            case 'daily':
                return current_date > self.last_rebalance
            case 'weekly':
                # Rebalance on Mondays
                return (current_date.weekday() == 0 and
                        current_date > self.last_rebalance)
            case 'monthly':
                # First trading day of month
                return (current_date.month != self.last_rebalance.month or
                        current_date.year != self.last_rebalance.year)
            case 'quarterly':
                curr_q = (current_date.month - 1) // 3
                last_q = (self.last_rebalance.month - 1) // 3
                return curr_q != last_q or current_date.year != self.last_rebalance.year
            case 'annually':
                return current_date.year != self.last_rebalance.year

        return False

    def generate_signals(self, market_data: pd.DataFrame, current_date: date) -> dict[str, float]:
        """Generate target allocations only on rebalance dates."""
        if not self.should_rebalance(current_date):
            return {}  # No rebalancing needed

        # Evaluate strategy to get target weights
        weights = self.compiled.evaluate(market_data)
        self.last_rebalance = current_date
        return weights
```

**Acceptance Criteria:**
- [ ] All rebalance frequencies implemented
- [ ] Backtest respects rebalance schedule
- [ ] Live trading respects rebalance schedule
- [ ] Integration tests for each frequency
- [ ] Edge cases: market holidays, weekends

---

## Phase 2: High Priority Fixes (Week 3-4)

### 2.1 Validation Error Detail Enhancement
**Priority:** High | **Effort:** 1 day | **Risk:** Low

**Files:** `libs/dsl/llamatrade_dsl/validator.py`

```python
@dataclass
class ValidationError:
    message: str
    location: SourceLocation | None
    severity: Literal['error', 'warning']
    code: str  # e.g., 'INVALID_INDICATOR', 'MISSING_ASSET'
    suggestions: list[str] = field(default_factory=list)

class Validator:
    def validate_indicator(self, indicator: Indicator) -> list[ValidationError]:
        errors = []
        if indicator.name not in SUPPORTED_INDICATORS:
            similar = find_similar(indicator.name, SUPPORTED_INDICATORS.keys())
            errors.append(ValidationError(
                message=f"Unknown indicator: {indicator.name}",
                location=indicator.location,
                severity='error',
                code='UNKNOWN_INDICATOR',
                suggestions=[f"Did you mean '{s}'?" for s in similar[:3]],
            ))
        return errors
```

**Acceptance Criteria:**
- [ ] All validation errors include location
- [ ] Error codes are consistent and documented
- [ ] Similar-name suggestions for typos
- [ ] Warnings for deprecated features

---

### 2.2 Division by Zero Protection
**Priority:** High | **Effort:** 1 day | **Risk:** Medium

**Files:** `libs/compiler/llamatrade_compiler/evaluator.py`

```python
def safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Division with zero handling - returns 0 where denominator is 0."""
    with np.errstate(divide='ignore', invalid='ignore'):
        result = np.where(denominator != 0, numerator / denominator, 0.0)
    return result

def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights to sum to 1, handling edge cases."""
    total = sum(weights.values())
    if total == 0 or not np.isfinite(total):
        # Equal weight fallback
        n = len(weights)
        return {k: 1.0 / n for k in weights} if n > 0 else {}
    return {k: v / total for k, v in weights.items()}
```

**Acceptance Criteria:**
- [ ] No division by zero exceptions
- [ ] NaN/Inf values handled gracefully
- [ ] Fallback behavior is documented
- [ ] Unit tests for edge cases

---

### 2.3 Race Condition Prevention in Store
**Priority:** High | **Effort:** 2 days | **Risk:** Medium

**Files:** `apps/web/src/store/strategy-builder.ts`

```typescript
// Add optimistic locking and debouncing
interface StrategyBuilderState {
  version: number;  // Incremented on each change
  isSaving: boolean;
  lastSavedVersion: number;
  pendingChanges: boolean;
}

const useStrategyBuilderStore = create<StrategyBuilderState>()(
  persist(
    (set, get) => ({
      // Debounced save
      saveStrategy: debounce(async () => {
        const state = get();
        if (state.isSaving) return;

        set({ isSaving: true });
        try {
          const result = await strategyService.updateStrategy({
            id: state.strategyId,
            dsl: toDSL(state.tree, state.metadata),
            version: state.version,  // Optimistic lock
          });

          if (result.conflict) {
            // Handle concurrent edit
            set({ conflictDetected: true });
          } else {
            set({ lastSavedVersion: state.version });
          }
        } finally {
          set({ isSaving: false });
        }
      }, 1000),

      // Atomic block operations
      addBlock: (parentId, block) => set((state) => {
        const newBlocks = { ...state.tree.blocks };
        const parent = { ...newBlocks[parentId] };
        // ... atomic update
        return {
          tree: { ...state.tree, blocks: newBlocks },
          version: state.version + 1,
          pendingChanges: true,
        };
      }),
    }),
    { name: 'strategy-builder' }
  )
);
```

**Acceptance Criteria:**
- [ ] Debounced auto-save prevents rapid fire
- [ ] Optimistic locking detects conflicts
- [ ] UI shows "unsaved changes" indicator
- [ ] Conflict resolution UI

---

### 2.4 Multi-Symbol Backtest Support
**Priority:** High | **Effort:** 2 days | **Risk:** Medium

**Files:** `services/backtest/src/engine/backtester.py`

```python
async def run_backtest(
    self,
    strategy: CompiledStrategy,
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> BacktestResult:
    """Run backtest for multi-symbol strategy."""
    # Fetch data for ALL symbols
    market_data = {}
    for symbol in symbols:
        market_data[symbol] = await self.market_data_client.get_bars(
            symbol, start_date, end_date
        )

    # Align dates across all symbols
    common_dates = self._get_common_dates(market_data)

    # Initialize portfolio
    portfolio = Portfolio(initial_cash=100_000)

    for date in common_dates:
        # Get current prices for all symbols
        prices = {s: market_data[s].loc[date, 'close'] for s in symbols}

        # Evaluate strategy to get target weights
        target_weights = strategy.evaluate(market_data, date)

        # Calculate required trades
        trades = portfolio.calculate_rebalance_trades(target_weights, prices)

        # Execute trades
        for trade in trades:
            portfolio.execute_trade(trade, prices[trade.symbol])

        # Record portfolio value
        portfolio.record_snapshot(date, prices)

    return self._calculate_metrics(portfolio)
```

**Acceptance Criteria:**
- [ ] Supports arbitrary number of symbols
- [ ] Handles missing data for individual symbols
- [ ] Proper date alignment across symbols
- [ ] Correct position sizing for portfolio

---

### 2.5 gRPC Error Handling Standardization
**Priority:** High | **Effort:** 1 day | **Risk:** Low

**Files:** All `services/*/src/grpc/servicer.py`

```python
from grpc import StatusCode
from llamatrade_proto.generated import Code

# Standard error mapping
DSL_ERROR_MAP = {
    'PARSE_ERROR': (Code.INVALID_ARGUMENT, 'Invalid strategy syntax'),
    'VALIDATION_ERROR': (Code.INVALID_ARGUMENT, 'Strategy validation failed'),
    'NOT_FOUND': (Code.NOT_FOUND, 'Strategy not found'),
    'PERMISSION_DENIED': (Code.PERMISSION_DENIED, 'Access denied'),
    'INTERNAL_ERROR': (Code.INTERNAL, 'Internal server error'),
}

def handle_dsl_error(error: DSLError) -> tuple[Code, str]:
    """Convert DSL error to gRPC status."""
    error_type = type(error).__name__
    code, base_msg = DSL_ERROR_MAP.get(
        error_type,
        (Code.INTERNAL, 'Unknown error')
    )

    # Include location if available
    if hasattr(error, 'location') and error.location:
        loc = error.location
        detail = f"{base_msg}: {error.message} at line {loc.line}, column {loc.column}"
    else:
        detail = f"{base_msg}: {error.message}"

    return code, detail
```

**Acceptance Criteria:**
- [ ] Consistent error codes across services
- [ ] Detailed error messages with locations
- [ ] Error codes documented in proto comments
- [ ] Frontend displays user-friendly messages

---

### 2.6 Database Constraint Additions
**Priority:** High | **Effort:** 1 day | **Risk:** Medium

**Files:**
- `libs/db/llamatrade_db/models/strategy.py`
- New migration file

```python
# models/strategy.py
class Strategy(Base):
    __tablename__ = 'strategies'

    id = Column(UUID, primary_key=True)
    tenant_id = Column(UUID, nullable=False, index=True)
    name = Column(String(255), nullable=False)

    __table_args__ = (
        # Unique name per tenant
        UniqueConstraint('tenant_id', 'name', name='uq_strategy_tenant_name'),
        # Index for common queries
        Index('ix_strategy_tenant_updated', 'tenant_id', 'updated_at'),
    )

class StrategyVersion(Base):
    __tablename__ = 'strategy_versions'

    id = Column(UUID, primary_key=True)
    strategy_id = Column(UUID, ForeignKey('strategies.id', ondelete='CASCADE'))
    version = Column(Integer, nullable=False)
    dsl_source = Column(Text, nullable=False)

    __table_args__ = (
        # Unique version per strategy
        UniqueConstraint('strategy_id', 'version', name='uq_version_strategy_version'),
        # Check constraint for positive version
        CheckConstraint('version > 0', name='ck_version_positive'),
    )
```

**Migration:**
```python
def upgrade():
    op.create_unique_constraint(
        'uq_strategy_tenant_name', 'strategies',
        ['tenant_id', 'name']
    )
    op.create_unique_constraint(
        'uq_version_strategy_version', 'strategy_versions',
        ['strategy_id', 'version']
    )
    op.create_check_constraint(
        'ck_version_positive', 'strategy_versions',
        'version > 0'
    )
```

**Acceptance Criteria:**
- [ ] Migration runs without data loss
- [ ] Duplicate names rejected at DB level
- [ ] Version uniqueness enforced
- [ ] Proper error messages on constraint violation

---

## Phase 3: Medium Priority Fixes (Week 5-6)

### 3.1 Escape Sequence Support in Strings
**Priority:** Medium | **Effort:** 0.5 days | **Risk:** Low

**Files:** `libs/dsl/llamatrade_dsl/parser.py`

```python
def _parse_string(self) -> str:
    """Parse string with escape sequence support."""
    token = self._expect("STRING")
    raw = token.value[1:-1]  # Remove quotes

    # Process escape sequences
    result = []
    i = 0
    while i < len(raw):
        if raw[i] == '\\' and i + 1 < len(raw):
            next_char = raw[i + 1]
            escape_map = {
                'n': '\n', 't': '\t', 'r': '\r',
                '\\': '\\', '"': '"',
            }
            if next_char in escape_map:
                result.append(escape_map[next_char])
                i += 2
                continue
        result.append(raw[i])
        i += 1

    return ''.join(result)
```

---

### 3.2 Comment Preservation in AST
**Priority:** Medium | **Effort:** 1 day | **Risk:** Low

**Files:** `libs/dsl/llamatrade_dsl/parser.py`, `ast.py`

```python
@dataclass
class Comment:
    text: str
    location: SourceLocation
    attached_to: ASTNode | None = None  # Comment before this node

@dataclass
class Strategy:
    # ... existing fields
    comments: list[Comment] = field(default_factory=list)
```

---

### 3.3 Indicator Parameter Validation
**Priority:** Medium | **Effort:** 1 day | **Risk:** Low

**Files:** `libs/dsl/llamatrade_dsl/validator.py`

```python
def validate_indicator_params(self, indicator: Indicator) -> list[ValidationError]:
    """Validate indicator parameters against spec."""
    spec = SUPPORTED_INDICATORS.get(indicator.name)
    if not spec:
        return [self._unknown_indicator_error(indicator)]

    errors = []

    # Check required params
    for param in spec['required_params']:
        if param not in indicator.params:
            errors.append(ValidationError(
                message=f"Missing required parameter '{param}' for {indicator.name}",
                location=indicator.location,
                code='MISSING_PARAM',
            ))

    # Validate param types and ranges
    for param, value in indicator.params.items():
        if param == 'period' and (not isinstance(value, int) or value < 1):
            errors.append(ValidationError(
                message=f"Period must be positive integer, got {value}",
                location=indicator.location,
                code='INVALID_PARAM_VALUE',
            ))

    return errors
```

---

### 3.4 UI State Persistence Optimization
**Priority:** Medium | **Effort:** 1 day | **Risk:** Low

**Files:**
- `apps/web/src/store/strategy-builder.ts`
- `services/strategy/src/services/strategy_service.py`

```typescript
// Store minimal UI state, not full block tree
interface MinimalUIState {
  expandedBlocks: string[];
  selectedBlockId: string | null;
  viewMode: 'visual' | 'code';
  zoom: number;
}

// Full block tree reconstructed from DSL on load
async function loadStrategy(id: string) {
  const response = await strategyService.getStrategy(id);
  const { tree, metadata } = fromDSLString(response.dsl_source);

  // Apply saved UI state
  const uiState = response.parameters?.ui_state as MinimalUIState;
  if (uiState) {
    applyUIState(tree, uiState);
  }

  return { tree, metadata, uiState };
}
```

---

### 3.5 Soft Delete Implementation
**Priority:** Medium | **Effort:** 1 day | **Risk:** Medium

**Files:**
- `libs/db/llamatrade_db/models/strategy.py`
- `services/strategy/src/services/strategy_service.py`

```python
class Strategy(Base):
    # ... existing fields
    deleted_at = Column(DateTime, nullable=True, index=True)

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

class StrategyService:
    async def delete_strategy(self, tenant_id: str, strategy_id: str) -> bool:
        """Soft delete strategy."""
        result = await self.db.execute(
            update(Strategy)
            .where(Strategy.tenant_id == tenant_id)
            .where(Strategy.id == strategy_id)
            .where(Strategy.deleted_at.is_(None))
            .values(deleted_at=datetime.utcnow())
        )
        return result.rowcount > 0

    async def list_strategies(self, tenant_id: str) -> list[Strategy]:
        """List non-deleted strategies."""
        return await self.db.scalars(
            select(Strategy)
            .where(Strategy.tenant_id == tenant_id)
            .where(Strategy.deleted_at.is_(None))
            .order_by(Strategy.updated_at.desc())
        )
```

---

### 3.6 Benchmark Comparison in Backtest
**Priority:** Medium | **Effort:** 2 days | **Risk:** Low

**Files:** `services/backtest/src/engine/benchmarks.py`

```python
class BenchmarkComparison:
    def __init__(self, benchmark_symbol: str = 'SPY'):
        self.benchmark = benchmark_symbol

    async def calculate_relative_metrics(
        self,
        portfolio_returns: pd.Series,
        market_data: pd.DataFrame,
    ) -> dict:
        benchmark_returns = market_data['close'].pct_change()

        # Alpha and Beta
        cov_matrix = np.cov(portfolio_returns, benchmark_returns)
        beta = cov_matrix[0, 1] / cov_matrix[1, 1]
        alpha = portfolio_returns.mean() - beta * benchmark_returns.mean()

        # Information Ratio
        tracking_error = (portfolio_returns - benchmark_returns).std()
        excess_return = portfolio_returns.mean() - benchmark_returns.mean()
        information_ratio = excess_return / tracking_error if tracking_error > 0 else 0

        # Treynor Ratio
        risk_free_rate = 0.02 / 252  # Daily
        treynor = (portfolio_returns.mean() - risk_free_rate) / beta if beta != 0 else 0

        return {
            'alpha': float(alpha * 252),  # Annualized
            'beta': float(beta),
            'information_ratio': float(information_ratio * np.sqrt(252)),
            'treynor_ratio': float(treynor * 252),
            'tracking_error': float(tracking_error * np.sqrt(252)),
        }
```

---

## Phase 4: Low Priority & Polish (Week 7-8)

### 4.1 Performance Optimizations
- Lazy compilation (compile on first use)
- Indicator result caching with LRU
- Batch market data requests
- Connection pooling tuning

### 4.2 Developer Experience
- CLI tool for DSL validation: `llamatrade dsl validate strategy.lisp`
- DSL playground/REPL for testing
- Better error messages with suggestions
- Auto-complete in code editor

### 4.3 Documentation
- DSL language reference
- Block type specifications
- Indicator parameter reference
- API documentation updates

### 4.4 Monitoring & Observability
- Metrics for compilation time
- Error rate tracking by error type
- Performance percentiles
- Alert thresholds

---

## Test Coverage Requirements

### Unit Tests (Per Phase)

| Component | Current | Phase 1 Target | Final Target |
|-----------|---------|----------------|--------------|
| Parser | ~40% | 80% | 95% |
| Validator | ~30% | 70% | 90% |
| Compiler | ~25% | 60% | 85% |
| Frontend Serializer | ~20% | 70% | 90% |
| Strategy Service | ~35% | 75% | 90% |

### Integration Tests Required

1. **DSL Round-Trip**
   - Frontend block tree → DSL → Backend parse → Execute → Results
   - Every block type combination

2. **Multi-Service Flow**
   - Create strategy → Validate → Compile → Backtest → Results

3. **Tenant Isolation**
   - Cross-tenant access attempts blocked
   - Proper error responses

4. **Error Propagation**
   - DSL errors surface with location
   - Validation errors show details
   - Compilation errors are actionable

---

## Dependency Graph

```
Phase 1 (Critical):
  1.1 Parser Locations ──┐
                         ├──► 2.1 Validation Details
  1.2 Indicator Registry ┘

  1.3 Frontend fromDSL ──► 3.4 UI State Persistence

  1.4 Transaction Safety ──► 2.6 DB Constraints

  1.5 Tenant Isolation (independent)

  1.6 Rebalancing ──► 2.4 Multi-Symbol Backtest

Phase 2 (High):
  2.1 Validation Details ──► 2.5 gRPC Errors
  2.2 Division Safety (independent)
  2.3 Race Conditions (independent)
  2.4 Multi-Symbol ──► 3.6 Benchmarks
  2.5 gRPC Errors (independent)
  2.6 DB Constraints (independent)

Phase 3 (Medium):
  3.1-3.6 (mostly independent, can parallelize)

Phase 4 (Low):
  4.1-4.4 (independent, can parallelize)
```

---

## Risk Mitigation

### High-Risk Items

1. **Transaction Safety Changes**
   - Risk: Breaking existing workflows
   - Mitigation: Feature flag, gradual rollout
   - Rollback: Disable transaction wrapper

2. **Tenant Isolation Event Hook**
   - Risk: Performance impact on queries
   - Mitigation: Benchmark before/after, caching
   - Rollback: Remove event listener

3. **Database Constraints**
   - Risk: Blocking existing duplicate data
   - Mitigation: Clean data first, then add constraints
   - Rollback: Drop constraints (migration down)

### Migration Strategy

1. Run data quality checks before Phase 2 migrations
2. Add constraints with `NOT VALID` first, then validate
3. Monitor error rates after each deployment
4. Keep rollback migrations ready

---

## Success Metrics

| Metric | Current | Phase 1 | Phase 2 | Final |
|--------|---------|---------|---------|-------|
| DSL Parse Errors | ~15% | <5% | <2% | <1% |
| Round-Trip Success | ~60% | 90% | 98% | 99.9% |
| Error Messages with Location | 0% | 80% | 95% | 100% |
| Test Coverage (avg) | ~30% | 70% | 80% | 90% |
| Backtest Success Rate | ~70% | 90% | 95% | 99% |

---

## Resource Allocation

### Recommended Team Split

| Phase | Backend | Frontend | Timeline |
|-------|---------|----------|----------|
| Phase 1 | 2 devs | 1 dev | 2 weeks |
| Phase 2 | 1 dev | 1 dev | 2 weeks |
| Phase 3 | 1 dev | 1 dev | 2 weeks |
| Phase 4 | 1 dev | 0.5 dev | 2 weeks |

### Critical Path

Week 1-2: Parser locations (1.1) + Indicator registry (1.2) + Transaction safety (1.4)
Week 2-3: Frontend fromDSL (1.3) + Rebalancing (1.6)
Week 3-4: Validation details (2.1) + Multi-symbol (2.4)
Week 5-6: Remaining Phase 2 + Phase 3 items
Week 7-8: Phase 4 polish and documentation

---

## Appendix: Issue Reference

Full issue list with IDs for tracking:

### Parser (DSL-P-*)
- DSL-P-01: Source location tracking [Critical]
- DSL-P-02: Escape sequences [Medium]
- DSL-P-03: Comment preservation [Medium]
- DSL-P-04: Better error recovery [Low]
- ... (11 more)

### Compiler (DSL-C-*)
- DSL-C-01: Indicator registry sync [Critical]
- DSL-C-02: Division by zero [High]
- DSL-C-03: NaN propagation [High]
- DSL-C-04: Memory efficiency [Medium]
- ... (11 more)

### Frontend (DSL-F-*)
- DSL-F-01: Complete fromDSL [Critical]
- DSL-F-02: Race conditions [High]
- DSL-F-03: Validation sync [High]
- DSL-F-04: Undo/redo [Medium]
- ... (24 more)

### Service/DB (DSL-S-*)
- DSL-S-01: Transaction safety [Critical]
- DSL-S-02: Tenant isolation [Critical]
- DSL-S-03: Unique constraints [High]
- DSL-S-04: Soft delete [Medium]
- ... (20 more)

### Execution (DSL-E-*)
- DSL-E-01: Rebalancing logic [Critical]
- DSL-E-02: Multi-symbol support [High]
- DSL-E-03: Position sizing [High]
- DSL-E-04: Benchmarks [Medium]
- ... (8 more)
