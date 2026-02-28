# Event Sourcing for Trading

Implementation specification for event sourcing in the trading service, providing durable execution, crash recovery, and complete audit trails.

---

## Overview

The trading service uses event sourcing to ensure:

- **Idempotent order submission** - Same signal always produces same order, even after crash
- **Crash recovery** - Replay events to reconstruct state
- **Complete audit trail** - Every action recorded as an immutable event
- **Time-travel debugging** - Reconstruct state at any point in time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STRATEGY RUNNER                                   │
│                                                                             │
│   Market Data ──► Strategy Logic ──► Signal ──► EventSourcedOrderExecutor  │
└───────────────────────────────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EVENT SOURCED EXECUTOR                               │
│                                                                             │
│   1. Generate deterministic client_order_id (SHA256 hash)                   │
│   2. Check Alpaca for existing order (crash recovery)                       │
│   3. Run risk checks                                                        │
│   4. Emit OrderSubmitted event                                              │
│   5. Submit to Alpaca with client_order_id                                  │
│   6. Emit OrderAccepted/OrderRejected event                                 │
│   7. Emit OrderFilled event on fill                                         │
└───────────────────────────────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EVENT STORE                                       │
│                                                                             │
│   trading_events table (append-only)                                        │
│   ├── sequence (auto-increment PK)                                          │
│   ├── event_id (UUID)                                                       │
│   ├── event_type (string)                                                   │
│   ├── tenant_id, session_id                                                 │
│   ├── timestamp                                                             │
│   └── data (JSONB payload)                                                  │
└───────────────────────────────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGGREGATES                                        │
│                                                                             │
│   SessionState.load(session_id) ◄── Replay events                           │
│   ├── positions: dict[symbol, PositionState]                                │
│   ├── orders: dict[order_id, OrderState]                                    │
│   ├── realized_pnl: Decimal                                                 │
│   └── metrics: signals, fills, cancels, etc.                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts

### Events

Events are immutable facts that have occurred. They are the source of truth.

**Properties:**
- Immutable once written
- Ordered by global sequence number
- Scoped to tenant + session
- Contain all data needed to understand what happened

**Example Event:**
```python
OrderFilled(
    event_id=UUID(...),
    tenant_id=UUID(...),
    session_id=UUID(...),
    timestamp=datetime.now(UTC),
    order_id=UUID(...),
    symbol="AAPL",
    side="buy",
    filled_qty=Decimal("100"),
    filled_avg_price=Decimal("150.50"),
)
```

### Aggregates

Aggregates are current state derived by replaying events. They provide the read model.

```python
# Load state by replaying all events
state = await SessionState.load(session_id, tenant_id, event_store)

# State contains derived data
state.positions["AAPL"]  # Current position
state.orders[order_id]   # Order status
state.realized_pnl       # Total realized P&L
```

### Idempotent Order Submission

Orders use deterministic `client_order_id` based on signal parameters:

```python
def generate_deterministic_order_id(
    session_id: UUID,
    symbol: str,
    side: str,
    signal_timestamp: datetime,
) -> str:
    data = f"{session_id}:{symbol}:{side}:{signal_timestamp.isoformat()}"
    hash_digest = hashlib.sha256(data.encode()).hexdigest()[:16]
    return f"lt-{hash_digest}"  # e.g., "lt-a1b2c3d4e5f6g7h8"
```

**Why this works:**
1. Same signal always produces same `client_order_id`
2. Alpaca treats `client_order_id` as idempotency key
3. If we crash after submitting but before recording, retry finds existing order
4. Prevents duplicate orders even with at-least-once delivery

---

## Event Types

Source: `services/trading/src/events/trading_events.py`

### Signal Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `signal.generated` | Strategy produced a trading signal | symbol, signal_type, price, qty, confidence, indicators |
| `signal.rejected` | Signal failed risk checks | symbol, signal_type, reason, details |

### Order Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `order.submitted` | Order sent to broker | order_id, client_order_id, symbol, side, qty, order_type |
| `order.accepted` | Broker accepted order | order_id, broker_order_id |
| `order.rejected` | Broker rejected order | order_id, reason, broker_message |
| `order.filled` | Order completely filled | order_id, filled_qty, filled_avg_price |
| `order.partially_filled` | Partial fill | order_id, filled_qty, remaining_qty |
| `order.cancelled` | Order cancelled | order_id, reason, filled_qty |

### Position Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `position.opened` | New position created | symbol, side, qty, entry_price, order_id |
| `position.increased` | Added to position | symbol, qty_added, price, new_avg_cost |
| `position.reduced` | Partial close | symbol, qty_removed, exit_price, realized_pnl |
| `position.closed` | Position fully closed | symbol, exit_price, realized_pnl |

### Session Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `session.started` | Trading session started | strategy_id, strategy_name, mode, symbols, starting_equity |
| `session.stopped` | Trading session stopped | reason, final_equity, total_pnl |
| `session.paused` | Session paused | reason |
| `session.resumed` | Session resumed | - |

### Circuit Breaker Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `circuit_breaker.triggered` | Trading halted | reason, details |
| `circuit_breaker.reset` | Trading can resume | was_forced |

### Reconciliation Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `reconciliation.performed` | Synced with broker | positions_added, positions_removed, discrepancies_found |
| `reconciliation.external_trade` | Detected external trade | symbol, side, qty, price, broker_order_id |

---

## Database Schema

Source: `libs/db/llamatrade_db/alembic/versions/20240501_000000_005_add_trading_events_table.py`

### trading_events Table

| Column | Type | Description |
|--------|------|-------------|
| `sequence` | BIGINT | Auto-increment primary key, global ordering |
| `event_id` | UUID | Unique event identifier |
| `event_type` | VARCHAR(100) | Event type string (e.g., "order.filled") |
| `tenant_id` | UUID | Tenant identifier |
| `session_id` | UUID | Trading session identifier |
| `timestamp` | TIMESTAMPTZ | When the event occurred |
| `stored_at` | TIMESTAMPTZ | When the event was persisted |
| `data` | JSONB | Full event payload |

**Indexes:**
- `ix_trading_events_session_seq` - (session_id, sequence) for stream reads
- `ix_trading_events_tenant_seq` - (tenant_id, sequence) for tenant queries
- `ix_trading_events_type_seq` - (event_type, sequence) for filtered reads
- `ix_trading_events_event_id` - (event_id) for deduplication

---

## Event Store API

Source: `services/trading/src/events/store.py`

```python
class EventStore:
    async def append(self, event: TradingEvent) -> int:
        """Append event, returns sequence number."""

    async def append_batch(self, events: list[TradingEvent]) -> list[int]:
        """Append multiple events atomically."""

    async def read_stream(
        self,
        session_id: UUID,
        from_sequence: int = 0,
        to_sequence: int | None = None,
        event_types: list[str] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[TradingEvent]:
        """Read events for a session in order."""

    async def read_all(
        self,
        tenant_id: UUID,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[TradingEvent]:
        """Read all events for a tenant."""

    async def get_by_id(self, event_id: UUID) -> TradingEvent | None:
        """Get specific event by ID."""

    async def get_latest_sequence(self, session_id: UUID) -> int:
        """Get highest sequence number for session."""
```

### Usage Example

```python
from src.events.store import EventStore, create_event_store
from src.events.trading_events import OrderSubmitted

# Create store
event_store = create_event_store(db_session)

# Append event
seq = await event_store.append(
    OrderSubmitted(
        tenant_id=tenant_id,
        session_id=session_id,
        order_id=order_id,
        client_order_id="lt-abc123",
        symbol="AAPL",
        side="buy",
        qty=Decimal("100"),
        order_type="market",
    )
)
print(f"Event stored at sequence {seq}")

# Read events
async for event in event_store.read_stream(session_id):
    print(f"{event.event_type}: {event.to_dict()}")
```

---

## Aggregates

Source: `services/trading/src/events/aggregates.py`

### SessionState

Main aggregate holding all session state.

```python
@dataclass
class SessionState:
    session_id: UUID
    tenant_id: UUID

    # Session info
    strategy_id: UUID | None
    strategy_name: str | None
    mode: Literal["live", "paper"] | None
    symbols: list[str]

    # Status
    status: str  # starting, active, paused, stopped, error
    circuit_breaker_triggered: bool
    circuit_breaker_reason: str | None

    # Derived state
    positions: dict[str, PositionState]
    orders: dict[UUID, OrderState]

    # Metrics
    starting_equity: Decimal
    realized_pnl: Decimal
    signals_generated: int
    signals_rejected: int
    orders_submitted: int
    orders_filled: int
    orders_cancelled: int
    orders_rejected: int

    # Version tracking
    version: int  # Last sequence applied
    events_applied: int

    def apply(self, event: TradingEvent) -> None:
        """Apply event to update state."""

    @classmethod
    async def load(
        cls,
        session_id: UUID,
        tenant_id: UUID,
        event_store: EventStore,
    ) -> "SessionState":
        """Load by replaying events."""

    def get_open_orders(self) -> list[OrderState]:
        """Get orders that are still open."""

    def get_position(self, symbol: str) -> PositionState | None:
        """Get position for symbol."""
```

### OrderState

```python
@dataclass
class OrderState:
    order_id: UUID
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: Decimal
    order_type: str
    time_in_force: str
    limit_price: Decimal | None
    stop_price: Decimal | None
    status: str  # pending, submitted, accepted, filled, partial, cancelled, rejected
    broker_order_id: str | None
    filled_qty: Decimal
    filled_avg_price: Decimal | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
```

### PositionState

```python
@dataclass
class PositionState:
    symbol: str
    side: Literal["long", "short"]
    qty: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal

    @property
    def market_value(self) -> Decimal:
        """qty * avg_cost"""

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L at given price."""
```

---

## Crash Recovery

The system handles crashes at any point in the order lifecycle.

### Scenario 1: Crash Before Alpaca Submission

```
1. Signal generated
2. OrderSubmitted event written
3. CRASH before Alpaca API call
```

**Recovery:**
- On restart, signal replays produce same deterministic client_order_id
- Check Alpaca: order doesn't exist
- Submit order normally

### Scenario 2: Crash After Alpaca Submission, Before Event

```
1. Signal generated
2. OrderSubmitted event written
3. Alpaca accepts order
4. CRASH before OrderAccepted event
```

**Recovery:**
- On restart, signal replays produce same deterministic client_order_id
- Check Alpaca: order exists with status
- Emit missing events (OrderAccepted, possibly OrderFilled)
- Skip re-submission

### Scenario 3: Recovery Process

```python
async def recover_from_crash(
    self,
    session_id: UUID,
    tenant_id: UUID,
) -> SessionState:
    """Recover session state after crash."""

    # 1. Load state from events
    state = await SessionState.load(session_id, tenant_id, self.events)

    # 2. Check open orders against Alpaca
    for order in state.get_open_orders():
        alpaca_order = await self.alpaca.get_order_by_client_id(
            order.client_order_id
        )

        if alpaca_order:
            # Emit any missing events
            await self._sync_order_events(
                tenant_id, session_id, order, alpaca_order
            )

    # 3. Return recovered state
    return await SessionState.load(session_id, tenant_id, self.events)
```

---

## Runner Integration

Source: `services/trading/src/runner/runner.py`

The StrategyRunner integrates event sourcing optionally:

```python
class StrategyRunner:
    def __init__(
        self,
        tenant_id: UUID,
        session_id: UUID,
        ...,
        event_store: EventStore | None = None,  # Optional
    ):
        self._event_store = event_store
        self._event_executor: EventSourcedOrderExecutor | None = None

        if event_store and alpaca_client:
            self._event_executor = EventSourcedOrderExecutor(
                event_store=event_store,
                alpaca_client=alpaca_client,
                risk_manager=risk_manager,
            )

    async def start(self) -> None:
        # Recover from crash if using event sourcing
        if self._event_executor:
            state = await self._event_executor.recover_from_crash(
                self.session_id, self.tenant_id
            )
            # Restore positions from event-sourced state
            for symbol, pos in state.positions.items():
                self._positions[symbol] = Position(
                    symbol=symbol,
                    qty=float(pos.qty),
                    side=pos.side,
                    avg_cost=float(pos.avg_cost),
                )

        # Emit SessionStarted event
        if self._event_store:
            await self._event_store.append(
                SessionStarted(
                    tenant_id=self.tenant_id,
                    session_id=self.session_id,
                    strategy_id=self._strategy_id,
                    strategy_name=self._strategy_name,
                    mode=self._mode,
                    symbols=list(self._symbols),
                    starting_equity=Decimal(str(self._current_equity)),
                )
            )
```

---

## Event Registration

Events are registered for deserialization via decorator:

```python
from src.events.base import TradingEvent, register_event

@register_event
@dataclass(kw_only=True)
class MyCustomEvent(TradingEvent):
    EVENT_TYPE: ClassVar[str] = "custom.my_event"

    my_field: str
    my_decimal: Decimal
```

The `@register_event` decorator adds the event class to a registry, enabling automatic deserialization:

```python
# Internally maintains:
_EVENT_REGISTRY["custom.my_event"] = MyCustomEvent

# Used by:
event = deserialize_event({"event_type": "custom.my_event", ...})
# Returns MyCustomEvent instance
```

---

## Testing

Source: `services/trading/tests/test_events.py`, `services/trading/tests/test_event_sourced_executor.py`

### Event Tests

```python
def test_order_lifecycle(self, session_ids):
    """Test full order lifecycle through events."""
    state = SessionState(...)

    # Submit
    submit_event = OrderSubmitted(...)
    state.apply(submit_event)
    assert state.orders[order_id].status == "submitted"

    # Accept
    accept_event = OrderAccepted(...)
    state.apply(accept_event)
    assert state.orders[order_id].status == "accepted"

    # Fill
    fill_event = OrderFilled(...)
    state.apply(fill_event)
    assert state.orders[order_id].status == "filled"
    assert state.orders_filled == 1
```

### Executor Tests

```python
async def test_submit_order_idempotent_on_existing(
    self, executor, mock_alpaca, mock_event_store, sample_order
):
    """Test that existing order in Alpaca is detected (crash recovery)."""
    mock_alpaca.get_order_by_client_id.return_value = {
        "id": "alpaca-existing",
        "status": "filled",
        "filled_qty": "100",
        "filled_avg_price": "150.50",
    }

    order_id = await executor.submit_order(...)

    # Should NOT call submit_order since order already exists
    mock_alpaca.submit_order.assert_not_called()

    # Should emit events based on existing order state
    assert mock_event_store.append.call_count >= 2
```

### Run Tests

```bash
cd services/trading

# Event tests
PYTHONPATH=. pytest tests/test_events.py -v

# Executor tests
PYTHONPATH=. pytest tests/test_event_sourced_executor.py -v

# All tests
PYTHONPATH=. pytest tests/ --ignore=tests/test_grpc_servicer.py -v
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `services/trading/src/events/__init__.py` | Package exports |
| `services/trading/src/events/base.py` | Base event class, registry, deserialization |
| `services/trading/src/events/trading_events.py` | All domain event definitions (18 events) |
| `services/trading/src/events/store.py` | PostgreSQL event store implementation |
| `services/trading/src/events/aggregates.py` | SessionState, OrderState, PositionState |
| `services/trading/src/executor/event_sourced_executor.py` | Idempotent order executor |
| `services/trading/src/runner/runner.py` | StrategyRunner with event sourcing integration |
| `libs/db/.../005_add_trading_events_table.py` | Database migration |
| `services/trading/tests/test_events.py` | Event and aggregate tests |
| `services/trading/tests/test_event_sourced_executor.py` | Executor tests |

---

## Future Enhancements

### Projections

Create read-optimized views from events:

```python
class TradeSummaryProjection:
    """Builds trade summary statistics from events."""

    async def rebuild(self, session_id: UUID) -> TradeSummary:
        trades = []
        async for event in event_store.read_stream(
            session_id,
            event_types=["position.closed"]
        ):
            trades.append(...)
        return TradeSummary(
            total_trades=len(trades),
            winning_trades=...,
            avg_return=...,
        )
```

### Snapshots

Optimize replay for long-running sessions:

```python
# Store snapshot every N events
if state.events_applied % 1000 == 0:
    await snapshot_store.save(state)

# Load from snapshot + replay recent events
snapshot = await snapshot_store.load(session_id)
state = SessionState.from_snapshot(snapshot)
async for event in event_store.read_stream(
    session_id,
    from_sequence=snapshot.version,
):
    state.apply(event)
```

### Event Archival

Archive old events to cold storage:

```python
# Move events older than 90 days to archive table
await archive_events(
    tenant_id=tenant_id,
    older_than=datetime.now(UTC) - timedelta(days=90),
)
```
