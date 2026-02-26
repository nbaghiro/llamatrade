# Strategy Builder Integration Plan

## Overview

Connect the frontend strategy builder (portfolio allocation tree with demo data) to the backend APIs for full end-to-end functionality: save/load strategies, run backtests, execute live trading.

## Current State Analysis

### Frontend (Implemented, No Backend Connection)
- **14 strategy builder components** in `apps/web/src/components/strategy-builder/`
- **Zustand store** at `apps/web/src/store/strategy-builder.ts` with undo/redo, demo data
- **Type definitions** at `apps/web/src/types/strategy-builder.ts`
- **No API services** - only bare axios instance exists at `apps/web/src/services/api.ts`
- **Stub pages**: StrategiesPage, StrategyEditorPage, BacktestPage, TradingPage all return placeholder UI

### Backend (APIs Exist, Never Called)
- `services/strategy/` - Full CRUD, versioning, deployments
- `services/backtest/` - Create, list, results, retry
- `services/trading/` - Sessions, orders, risk management
- `services/portfolio/` - Holdings, performance

### Critical Gap: Data Format Mismatch
- **Frontend**: Portfolio allocation tree (Root → Groups → Assets with weights)
- **Backend**: S-expression DSL for indicator-based strategies like `(sma 14 close)`

---

## Implementation Plan

### Sprint 1: Serialization & Core Persistence

**Goal**: Save and load strategy builder state to/from backend

#### 1.1 Create Serialization Layer
**File**: `apps/web/src/utils/strategy-serializer.ts`

```typescript
// Convert strategy builder tree → backend format
export function serializeStrategy(tree: StrategyTree): StrategyDefinition
// Convert backend format → strategy builder tree
export function deserializeStrategy(def: StrategyDefinition): StrategyTree
```

**Backend format** (extend existing S-expression to support portfolio allocation):
```json
{
  "type": "portfolio_allocation",
  "name": "My Strategy",
  "rebalance_frequency": "monthly",
  "tree": {
    "type": "root",
    "children": [
      {
        "type": "group",
        "name": "US Equities",
        "weight_method": "equal",
        "weight": 0.6,
        "children": [
          {"type": "asset", "symbol": "AAPL", "weight": null},
          {"type": "asset", "symbol": "GOOGL", "weight": null}
        ]
      }
    ]
  }
}
```

#### 1.2 Create API Client Services
**File**: `apps/web/src/services/strategies.ts`

```typescript
export const strategyService = {
  list: () => api.get<StrategyListResponse>('/api/strategies'),
  get: (id: string) => api.get<StrategyResponse>(`/api/strategies/${id}`),
  create: (data: StrategyCreate) => api.post<StrategyResponse>('/api/strategies', data),
  update: (id: string, data: StrategyUpdate) => api.put<StrategyResponse>(`/api/strategies/${id}`, data),
  delete: (id: string) => api.delete(`/api/strategies/${id}`),
}
```

#### 1.3 Update Strategy Builder Store
**File**: `apps/web/src/store/strategy-builder.ts`

Add actions:
```typescript
saveStrategy: async () => { /* serialize + POST/PUT */ }
loadStrategy: async (id: string) => { /* GET + deserialize */ }
setStrategyId: (id: string | null) => void
setSaveStatus: (status: 'idle' | 'saving' | 'saved' | 'error') => void
```

#### 1.4 Wire Up StrategyEditorPage
**File**: `apps/web/src/pages/StrategyEditorPage.tsx`

- Load strategy from URL param `?id=xxx` on mount
- Auto-save on changes (debounced)
- Show save status indicator
- Handle new vs edit mode

**Files to modify**:
- `apps/web/src/utils/strategy-serializer.ts` (new)
- `apps/web/src/services/strategies.ts` (new)
- `apps/web/src/store/strategy-builder.ts`
- `apps/web/src/pages/StrategyEditorPage.tsx`

---

### Sprint 2: Strategies List Page

**Goal**: View, create, edit, delete strategies

#### 2.1 Build Strategies API Service (completed in Sprint 1)

#### 2.2 Create Strategy List Store
**File**: `apps/web/src/store/strategies.ts`

```typescript
interface StrategiesStore {
  strategies: Strategy[]
  loading: boolean
  error: string | null
  fetchStrategies: () => Promise<void>
  deleteStrategy: (id: string) => Promise<void>
}
```

#### 2.3 Implement StrategiesPage
**File**: `apps/web/src/pages/StrategiesPage.tsx`

- List all strategies with name, status, last modified
- "New Strategy" button → navigate to editor
- Click row → navigate to editor with `?id=xxx`
- Delete with confirmation modal
- Show deployed vs draft status

**Files to modify**:
- `apps/web/src/store/strategies.ts` (new)
- `apps/web/src/pages/StrategiesPage.tsx`
- `apps/web/src/types/strategy.ts` (new - API types)

---

### Sprint 3: Backtest Integration

**Goal**: Run backtests from strategy builder and view results

#### 3.1 Create Backtest API Service
**File**: `apps/web/src/services/backtests.ts`

```typescript
export const backtestService = {
  create: (strategyId: string, config: BacktestConfig) => api.post('/api/backtests', {...}),
  get: (id: string) => api.get<BacktestResult>(`/api/backtests/${id}`),
  list: (strategyId?: string) => api.get<BacktestListResponse>('/api/backtests', {params: {strategy_id}}),
}
```

#### 3.2 Add Backtest Panel to Strategy Builder
**File**: `apps/web/src/components/strategy-builder/BacktestPanel.tsx` (new)

- Date range picker (start/end)
- Initial capital input
- Benchmark selection (SPY, QQQ, etc.)
- "Run Backtest" button
- Results display: total return, sharpe, max drawdown, chart

#### 3.3 Update BacktestPage
**File**: `apps/web/src/pages/BacktestPage.tsx`

- List all backtests with strategy name, date, status
- Click to view detailed results
- Re-run backtest option
- Compare multiple backtests

**Files to modify**:
- `apps/web/src/services/backtests.ts` (new)
- `apps/web/src/components/strategy-builder/BacktestPanel.tsx` (new)
- `apps/web/src/pages/BacktestPage.tsx`
- `apps/web/src/store/backtests.ts` (new)

---

### Sprint 4: Credentials & Trading Management

**Goal**: Connect broker accounts and execute strategies

#### 4.1 Backend: Credentials Endpoints (NEW)
**File**: `services/auth/src/routers/credentials.py` (new)

```python
@router.post("/credentials/alpaca")
async def save_alpaca_credentials(data: AlpacaCredentials, ctx: TenantContext):
    """Save encrypted Alpaca API keys"""

@router.get("/credentials/alpaca/status")
async def check_alpaca_status(ctx: TenantContext):
    """Return connection status without exposing keys"""

@router.delete("/credentials/alpaca")
async def delete_alpaca_credentials(ctx: TenantContext):
    """Remove stored credentials"""
```

#### 4.2 Frontend: Settings Page Credentials Section
**File**: `apps/web/src/pages/SettingsPage.tsx`

- Alpaca API key input (masked after save)
- Paper vs Live trading toggle
- Connection status indicator
- Test connection button

#### 4.3 Create Trading API Service
**File**: `apps/web/src/services/trading.ts`

```typescript
export const tradingService = {
  createSession: (strategyId: string, mode: 'paper' | 'live') => api.post('/api/sessions', {...}),
  getSession: (id: string) => api.get(`/api/sessions/${id}`),
  pauseSession: (id: string) => api.post(`/api/sessions/${id}/pause`),
  resumeSession: (id: string) => api.post(`/api/sessions/${id}/resume`),
  stopSession: (id: string) => api.post(`/api/sessions/${id}/stop`),
}
```

#### 4.4 Update TradingPage
**File**: `apps/web/src/pages/TradingPage.tsx`

- List active trading sessions
- Start new session (select strategy, paper/live)
- Session controls: pause, resume, stop
- Real-time P&L display
- Order history feed

**Files to modify**:
- `services/auth/src/routers/credentials.py` (new)
- `libs/db/llamatrade_db/models/credentials.py` (new)
- `apps/web/src/services/trading.ts` (new)
- `apps/web/src/pages/SettingsPage.tsx`
- `apps/web/src/pages/TradingPage.tsx`
- `apps/web/src/store/trading.ts` (new)

---

### Sprint 5: Funding & Capital Allocation (NEW ENDPOINTS)

**Goal**: Allocate capital to strategies

#### 5.1 Backend: Funding Endpoints
**File**: `services/portfolio/src/routers/funding.py` (new)

```python
@router.get("/funding/available")
async def get_available_capital(ctx: TenantContext):
    """Get unallocated cash from Alpaca account"""

@router.post("/funding/allocate")
async def allocate_to_strategy(data: AllocationRequest, ctx: TenantContext):
    """Reserve capital for a strategy"""

@router.get("/funding/allocations")
async def list_allocations(ctx: TenantContext):
    """Show capital allocated to each strategy"""

@router.post("/funding/deallocate")
async def deallocate_from_strategy(data: DeallocationRequest, ctx: TenantContext):
    """Release capital from a strategy"""
```

#### 5.2 Frontend: Funding Modal in Strategy Builder
**File**: `apps/web/src/components/strategy-builder/FundingModal.tsx` (new)

- Show available capital
- Input allocation amount
- Show current allocation if editing
- Confirm/cancel buttons

#### 5.3 Deploy Strategy Flow
**File**: `apps/web/src/components/strategy-builder/DeployModal.tsx` (new)

- Step 1: Select paper or live
- Step 2: Allocate capital (required for live)
- Step 3: Confirm deployment
- Creates trading session on confirm

**Files to modify**:
- `services/portfolio/src/routers/funding.py` (new)
- `services/portfolio/src/services/funding_service.py` (new)
- `apps/web/src/services/funding.ts` (new)
- `apps/web/src/components/strategy-builder/FundingModal.tsx` (new)
- `apps/web/src/components/strategy-builder/DeployModal.tsx` (new)

---

## Backend Changes Summary

### New Endpoints Required

| Service | Endpoint | Method | Description |
|---------|----------|--------|-------------|
| auth | /credentials/alpaca | POST | Save encrypted API keys |
| auth | /credentials/alpaca/status | GET | Check connection status |
| auth | /credentials/alpaca | DELETE | Remove credentials |
| portfolio | /funding/available | GET | Unallocated capital |
| portfolio | /funding/allocate | POST | Reserve capital for strategy |
| portfolio | /funding/allocations | GET | List all allocations |
| portfolio | /funding/deallocate | POST | Release capital |

### Database Models Required

1. **Credentials** (`libs/db/llamatrade_db/models/credentials.py`)
   - `tenant_id`, `provider` (alpaca), `encrypted_key`, `encrypted_secret`, `is_paper`

2. **StrategyAllocation** (`libs/db/llamatrade_db/models/allocation.py`)
   - `tenant_id`, `strategy_id`, `allocated_amount`, `created_at`

---

## File Summary

### New Files (Frontend)
- `apps/web/src/utils/strategy-serializer.ts`
- `apps/web/src/services/strategies.ts`
- `apps/web/src/services/backtests.ts`
- `apps/web/src/services/trading.ts`
- `apps/web/src/services/funding.ts`
- `apps/web/src/store/strategies.ts`
- `apps/web/src/store/backtests.ts`
- `apps/web/src/store/trading.ts`
- `apps/web/src/types/strategy.ts`
- `apps/web/src/components/strategy-builder/BacktestPanel.tsx`
- `apps/web/src/components/strategy-builder/FundingModal.tsx`
- `apps/web/src/components/strategy-builder/DeployModal.tsx`

### Modified Files (Frontend)
- `apps/web/src/store/strategy-builder.ts`
- `apps/web/src/pages/StrategiesPage.tsx`
- `apps/web/src/pages/StrategyEditorPage.tsx`
- `apps/web/src/pages/BacktestPage.tsx`
- `apps/web/src/pages/TradingPage.tsx`
- `apps/web/src/pages/SettingsPage.tsx`

### New Files (Backend)
- `services/auth/src/routers/credentials.py`
- `services/portfolio/src/routers/funding.py`
- `services/portfolio/src/services/funding_service.py`
- `libs/db/llamatrade_db/models/credentials.py`
- `libs/db/llamatrade_db/models/allocation.py`

---

## Verification Plan

### Sprint 1 Verification
1. Create new strategy in UI → verify saved to database
2. Refresh page → verify strategy loads correctly
3. Edit strategy → verify changes persist
4. Check serialization round-trip preserves all data

### Sprint 2 Verification
1. Navigate to /strategies → see list of saved strategies
2. Click "New" → redirects to empty editor
3. Click existing → opens in editor with data loaded
4. Delete → removed from list and database

### Sprint 3 Verification
1. Click "Run Backtest" → job created in backend
2. Poll until complete → results display
3. Verify metrics: returns, sharpe, drawdown calculations
4. Compare results match expected for known test data

### Sprint 4 Verification
1. Save Alpaca keys in Settings → verify encrypted storage
2. Test connection → shows success/failure status
3. Start paper trading session → session appears in Trading page
4. Verify orders flow through to Alpaca paper account

### Sprint 5 Verification
1. Check available capital matches Alpaca account
2. Allocate $10,000 to strategy → reflected in allocations
3. Start trading session → uses allocated capital
4. Deallocate → capital returns to available pool

---

## Implementation Order

1. **Sprint 1** (Core persistence) - Required first, everything depends on save/load
2. **Sprint 2** (Strategies list) - Natural next step, completes basic CRUD
3. **Sprint 3** (Backtesting) - Can be done in parallel with Sprint 4
4. **Sprint 4** (Credentials & Trading) - Can be done in parallel with Sprint 3
5. **Sprint 5** (Funding) - Depends on Sprint 4 (needs credentials working)

Estimated total: 5 implementation phases with clear dependencies.
