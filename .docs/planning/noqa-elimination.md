# Plan: Eliminate All `# noqa` Suppressions

Remove all 38 `# noqa` directives by fixing root causes.

---

## Summary

| Rule | Count | Fix Approach | Effort |
|------|-------|--------------|--------|
| E712 | 18 | Use SQLAlchemy `.is_(True/False)` | Low |
| F401 | 12 | Use `__all__`, `pytest_plugins`, or `_` prefix | Low |
| F841 | 4 | Remove variable assignment or use `_` | Trivial |
| N802 | 2 | Use `Mock(spec=...)` or rename | Low |
| N805 | 1 | Use `@classmethod` with `@declared_attr` | Trivial |
| C901 | 1 | Refactor into smaller functions | Medium |

---

## 1. E712: SQLAlchemy Boolean Comparisons (18 instances)

### Problem

```python
.where(Position.is_open == True)  # noqa: E712
```

Linter wants `is True` but SQLAlchemy requires `==` for SQL generation.

### Solution

Use SQLAlchemy's `.is_()` method:

```python
# Before
.where(Position.is_open == True)  # noqa: E712

# After
.where(Position.is_open.is_(True))
```

This generates the same SQL (`WHERE is_open IS TRUE`) and satisfies the linter.

### Files to Update

| File | Count |
|------|-------|
| `services/trading/src/services/position_service.py` | 6 |
| `services/trading/src/services/session_service.py` | 2 |
| `services/trading/src/services/alert_service.py` | 1 |
| `services/trading/src/services/live_session_service.py` | 1 |
| `services/trading/src/risk/risk_manager.py` | 2 |
| `services/billing/src/services/billing_service.py` | 2 |
| `services/auth/src/services/tenant_service.py` | 1 |
| `services/auth/src/grpc/servicer.py` | 2 |
| `tests/integration/services/test_strategy_db.py` | 1 |
| `tests/integration/services/test_trading_db.py` | 3 |

### Implementation

```bash
# Find and replace pattern
# == True  →  .is_(True)
# == False →  .is_(False)
```

---

## 2. F401: Unused Imports (12 instances)

### Problem

Imports exist for side effects but appear "unused" to the linter.

### Solution by Category

#### 2a. Test Fixture Imports (5 in `tests/conftest.py`)

**Before:**
```python
import tests.integration.fixtures.auth  # noqa: F401
import tests.integration.fixtures.backtest  # noqa: F401
```

**After:** Use `pytest_plugins` (pytest's official mechanism):
```python
pytest_plugins = [
    "tests.integration.fixtures.auth",
    "tests.integration.fixtures.backtest",
    "tests.integration.fixtures.orders",
    "tests.integration.fixtures.strategies",
    "tests.integration.fixtures.trading",
]
```

#### 2b. Proto Re-exports (5 in `tests/factories.py`)

**Before:**
```python
from llamatrade_proto.generated.backtest_pb2 import (  # noqa: F401
    BacktestResult,
    ...
)
```

**After:** Add explicit `__all__` to declare intentional re-exports:
```python
from llamatrade_proto.generated.backtest_pb2 import (
    BacktestResult,
    ...
)

__all__ = [
    "BacktestResult",
    ...
]
```

#### 2c. Alembic Model Discovery (1 in `libs/db/llamatrade_db/alembic/env.py`)

**Before:**
```python
from llamatrade_db.models import (  # noqa: F401
    User, Tenant, ...
)
```

**After:** Reference the import to make it "used":
```python
from llamatrade_db.models import (
    User, Tenant, ...
)

# Register models with metadata for autogenerate
_models = [User, Tenant, ...]  # Ensures models are imported
```

Or use `__all__` if this file is meant to re-export.

#### 2d. Integration Test Model Import (1 in `tests/integration/conftest.py`)

Same approach as 2c — either `__all__` or explicit reference.

---

## 3. F841: Unused Variables (4 instances)

### Problem

```python
_result = await interceptor.intercept_service(...)  # noqa: F841
```

Variable assigned but never used (testing that no exception is raised).

### Solution

Simply don't assign, or use `_` which is conventionally ignored:

```python
# Before
_result = await interceptor.intercept_service(...)  # noqa: F841

# After (Option A: no assignment)
await interceptor.intercept_service(...)

# After (Option B: underscore prefix, some linters ignore)
_ = await interceptor.intercept_service(...)
```

### Files to Update

| File | Count |
|------|-------|
| `libs/proto/tests/test_interceptors_auth.py` | 2 |
| `libs/proto/tests/test_clients_base.py` | 3 |

---

## 4. N802: Function Name Not Lowercase (2 instances)

### Problem

```python
def HasField(self, field):  # noqa: N802
```

Mocking protobuf's `HasField` method which uses CamelCase.

### Solution

Use `unittest.mock.Mock` with attribute assignment:

```python
# Before
class MockRequest:
    def HasField(self, field):  # noqa: N802
        return field in self._fields

# After
from unittest.mock import Mock

mock_request = Mock()
mock_request.HasField = lambda field: field in some_fields
```

Or use `create_autospec` with the actual protobuf message class.

### Files to Update

- `services/market-data/tests/test_grpc_servicer.py` (lines 127, 158)

---

## 5. N805: First Argument Should Be `self` (1 instance)

### Problem

```python
# libs/db/llamatrade_db/base.py
@declared_attr
def __table_args__(cls) -> TableArgsType:  # noqa: N805
```

SQLAlchemy's `@declared_attr` receives the class, so `cls` is semantically correct.

### Solution

Stack `@classmethod` with `@declared_attr`:

```python
# Before
@declared_attr
def __table_args__(cls) -> TableArgsType:  # noqa: N805
    ...

# After
@declared_attr
@classmethod
def __table_args__(cls) -> TableArgsType:
    ...
```

SQLAlchemy 2.0+ supports this pattern and the linter recognizes `cls` as valid for classmethods.

---

## 6. C901: Function Too Complex (1 instance)

### Problem

```python
# services/backtest/src/services/backtest_service.py:868
def _to_result_response(  # noqa: C901
```

Function has too many branches/complexity.

### Solution

Refactor into smaller, focused helper functions:

```python
# Before: One large function with many conditionals
def _to_result_response(self, result, backtest) -> BacktestResultResponse:
    # 50+ lines with many if/else branches
    ...

# After: Break into logical units
def _to_result_response(self, result, backtest) -> BacktestResultResponse:
    return BacktestResultResponse(
        metrics=self._build_metrics(result),
        equity_curve=self._build_equity_curve(result),
        trades=self._build_trades(result),
        benchmark=self._build_benchmark(result, backtest),
    )

def _build_metrics(self, result) -> Metrics:
    ...

def _build_equity_curve(self, result) -> list[EquityPoint]:
    ...

def _build_trades(self, result) -> list[Trade]:
    ...

def _build_benchmark(self, result, backtest) -> BenchmarkComparison | None:
    ...
```

---

## Implementation Order

### Phase 1: Trivial Fixes (30 min)
1. **F841** (4) — Remove variable assignments
2. **N805** (1) — Add `@classmethod` decorator

### Phase 2: Low Effort (1-2 hours)
3. **E712** (18) — Replace `== True/False` with `.is_(True/False)`
4. **F401** (12) — Add `__all__`, `pytest_plugins`, or explicit refs
5. **N802** (2) — Refactor mock classes to use `Mock()`

### Phase 3: Medium Effort (2-3 hours)
6. **C901** (1) — Refactor `_to_result_response` into smaller functions

---

## Verification

After all changes:

```bash
# Run linter to verify no noqa needed
ruff check services/ libs/ tests/ --select=E712,F401,F841,N802,N805,C901

# Verify no noqa comments remain
grep -r "# noqa" services/ libs/ tests/ --include="*.py"

# Run tests to ensure nothing broke
make test
```

---

## Notes

- All fixes maintain identical runtime behavior
- E712 fix (`.is_()`) generates slightly different but semantically equivalent SQL
- C901 refactor improves maintainability beyond just linter compliance
