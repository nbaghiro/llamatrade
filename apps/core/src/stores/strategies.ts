// Strategies list store — shared by web (StrategiesPage) and mobile.

import { create } from 'zustand';

import { BacktestStatus, type BacktestRun } from '../proto/backtest_pb';
import { ExecutionMode, ExecutionStatus, type Decimal } from '../proto/common_pb';
import { StrategyStatus, type Strategy } from '../proto/strategy_pb';
import { backtestClient, getTenantContext, portfolioClient, strategyClient } from '../net';

function decimalToNumber(d: Decimal | undefined): number {
  return d?.value ? parseFloat(d.value) : 0;
}

export type SortColumn = 'return' | 'sharpe' | 'allocation' | 'updated';
export type SortDirection = 'asc' | 'desc';

/** Live-deployment figures for a strategy, keyed by strategy id. */
export interface StrategyDeployment {
  allocatedCapital: number;
  currentValue: number;
  mode: ExecutionMode;
  status: ExecutionStatus;
  returnAll: number; // realized return, percent
  color: string; // backend series color, shared with dashboard/portfolio
}

// Map UI status strings to proto enum values
function parseStatusFilter(status: string): StrategyStatus[] | undefined {
  switch (status) {
    case 'draft':
      return [StrategyStatus.DRAFT];
    case 'active':
      return [StrategyStatus.ACTIVE];
    case 'paused':
      return [StrategyStatus.PAUSED];
    case 'archived':
      return [StrategyStatus.ARCHIVED];
    default:
      return undefined; // 'all' - no filter
  }
}

interface StrategiesState {
  // Data
  strategies: Strategy[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;

  // Fully-hydrated strategies keyed by id; the list returns summaries without the DSL, hydrated on demand via GetStrategy.
  details: Record<string, Strategy>;
  detailLoading: Record<string, boolean>;

  // Live-deployment figures (allocation, mode, realized return) keyed by strategy id.
  deployments: Record<string, StrategyDeployment>;

  // Latest completed backtest total return (percent) keyed by strategy id — the
  // return fallback for strategies that aren't deployed (draft/paused).
  backtestReturns: Record<string, number>;

  // Latest completed backtest RUN (full results: metrics, curves, holdings) keyed
  // by strategy id, for the detail screen. `null` = fetched, none found.
  runs: Record<string, BacktestRun | null>;
  runLoading: Record<string, boolean>;

  // Filters
  statusFilter: string;
  searchQuery: string;

  // Table sort
  sortColumn: SortColumn;
  sortDirection: SortDirection;

  // Async state
  loading: boolean;
  error: string | null;

  // Actions
  fetchStrategies: () => Promise<void>;
  fetchStrategyDetail: (id: string) => Promise<void>;
  fetchDeployments: () => Promise<void>;
  fetchBacktestReturns: () => Promise<void>;
  fetchStrategyRun: (id: string) => Promise<void>;
  setSort: (column: SortColumn) => void;
  setPage: (page: number) => void;
  setStatusFilter: (status: string) => void;
  setSearchQuery: (query: string) => void;
  deleteStrategy: (id: string) => Promise<void>;
  activateStrategy: (id: string) => Promise<void>;
  pauseStrategy: (id: string) => Promise<void>;
  cloneStrategy: (id: string, newName?: string) => Promise<string | null>;
  clearError: () => void;
}

export const useStrategiesStore = create<StrategiesState>((set, get) => ({
  // Initial state
  strategies: [],
  total: 0,
  page: 1,
  pageSize: 12,
  totalPages: 0,

  details: {},
  detailLoading: {},

  deployments: {},
  backtestReturns: {},
  runs: {},
  runLoading: {},

  statusFilter: 'all',
  searchQuery: '',

  sortColumn: 'return',
  sortDirection: 'desc',

  loading: false,
  error: null,

  fetchStrategies: async () => {
    const { page, pageSize, statusFilter, searchQuery } = get();

    set({ loading: true, error: null });

    // Get tenant context (will be undefined if not authenticated)
    const context = getTenantContext();
    if (!context) {
      set({
        error: 'Please log in to view your strategies',
        loading: false,
      });
      return;
    }

    try {
      const response = await strategyClient.listStrategies({
        context,
        pagination: { page, pageSize },
        statuses: parseStatusFilter(statusFilter),
        search: searchQuery || undefined,
      });

      const pagination = response.pagination;
      set({
        strategies: response.strategies,
        total: pagination?.totalItems ?? response.strategies.length,
        totalPages: pagination?.totalPages ?? 1,
        // Drop hydrated details so a refreshed list re-hydrates on demand,
        // picking up any new versions created since the last fetch.
        details: {},
        detailLoading: {},
        loading: false,
      });
    } catch (error) {
      // Check for authentication errors
      const errorMessage = error instanceof Error ? error.message : String(error);
      const isAuthError =
        errorMessage.includes('401') ||
        errorMessage.includes('Unauthorized') ||
        errorMessage.includes('unauthenticated');

      set({
        error: isAuthError
          ? 'Please log in to view your strategies'
          : error instanceof Error
            ? error.message
            : 'Failed to fetch strategies',
        loading: false,
      });
    }
  },

  // Hydrate one strategy's full detail for the drawer; cached by id, non-blocking (falls back to the list summary).
  fetchStrategyDetail: async (id) => {
    const { details, detailLoading } = get();
    if (details[id] || detailLoading[id]) return;

    const context = getTenantContext();
    if (!context) return;

    set((state) => ({ detailLoading: { ...state.detailLoading, [id]: true } }));
    try {
      const response = await strategyClient.getStrategy({ context, strategyId: id });
      const full = response.strategy;
      if (full) {
        set((state) => ({ details: { ...state.details, [id]: full } }));
      }
    } catch {
      // Swallow: caller can retry; the summary row still renders.
    } finally {
      set((state) => {
        const next = { ...state.detailLoading };
        delete next[id];
        return { detailLoading: next };
      });
    }
  },

  // Live-deployment figures from the portfolio service; non-blocking, largest execution wins.
  fetchDeployments: async () => {
    const context = getTenantContext();
    if (!context) {
      set({ deployments: {} });
      return;
    }

    try {
      const response = await portfolioClient.listStrategyPerformance({
        context,
        pagination: { page: 1, pageSize: 100 },
      });

      const deployments: Record<string, StrategyDeployment> = {};
      for (const s of response.strategies) {
        const next: StrategyDeployment = {
          allocatedCapital: decimalToNumber(s.allocatedCapital),
          currentValue: decimalToNumber(s.currentValue),
          mode: s.mode,
          status: s.status,
          returnAll: decimalToNumber(s.returns?.returnAll),
          color: s.color,
        };
        const existing = deployments[s.strategyId];
        if (!existing || next.allocatedCapital > existing.allocatedCapital) {
          deployments[s.strategyId] = next;
        }
      }
      set({ deployments });
    } catch {
      set({ deployments: {} });
    }
  },

  // Latest completed backtest return per strategy — the return shown for strategies
  // that aren't deployed. Summaries carry no metrics, so the latest run per strategy
  // is hydrated via GetBacktest. Non-blocking: degrades to empty on failure.
  fetchBacktestReturns: async () => {
    const context = getTenantContext();
    if (!context) {
      set({ backtestReturns: {} });
      return;
    }

    try {
      const response = await backtestClient.listBacktests({
        context,
        strategyId: '',
        pagination: { page: 1, pageSize: 50 },
      });

      const runTime = (b: BacktestRun): number =>
        Number(b.completedAt?.seconds ?? b.createdAt?.seconds ?? 0);

      const latest = new Map<string, BacktestRun>();
      for (const b of response.backtests
        .filter((b) => b.status === BacktestStatus.COMPLETED)
        .sort((a, b) => runTime(b) - runTime(a))) {
        if (!latest.has(b.strategyId)) latest.set(b.strategyId, b);
      }

      const entries = await Promise.all(
        [...latest.values()].map(async (b) => {
          try {
            const r = await backtestClient.getBacktest({ context, backtestId: b.id });
            const total = r.backtest?.results?.metrics?.totalReturn;
            // Wire stores fractions (0.12 = 12%); render as percent.
            return total?.value ? ([b.strategyId, parseFloat(total.value) * 100] as const) : null;
          } catch {
            return null;
          }
        }),
      );

      const backtestReturns: Record<string, number> = {};
      for (const e of entries) if (e) backtestReturns[e[0]] = e[1];
      set({ backtestReturns });
    } catch {
      set({ backtestReturns: {} });
    }
  },

  // Latest completed backtest RUN (full results) for one strategy — powers the
  // detail screen's metrics, equity chart, and holdings. Cached by strategy id.
  fetchStrategyRun: async (id) => {
    const { runs, runLoading } = get();
    if (id in runs || runLoading[id]) return;

    const context = getTenantContext();
    if (!context) return;

    set((state) => ({ runLoading: { ...state.runLoading, [id]: true } }));
    try {
      const list = await backtestClient.listBacktests({
        context,
        strategyId: id,
        pagination: { page: 1, pageSize: 20 },
      });
      const runTime = (b: BacktestRun): number =>
        Number(b.completedAt?.seconds ?? b.createdAt?.seconds ?? 0);
      const latest = list.backtests
        .filter((b) => b.status === BacktestStatus.COMPLETED)
        .sort((a, b) => runTime(b) - runTime(a))[0];

      let run: BacktestRun | null = null;
      if (latest) {
        const r = await backtestClient.getBacktest({ context, backtestId: latest.id });
        run = r.backtest ?? null;
      }
      set((state) => ({ runs: { ...state.runs, [id]: run } }));
    } catch {
      // Leave unset so the caller can retry.
    } finally {
      set((state) => {
        const next = { ...state.runLoading };
        delete next[id];
        return { runLoading: next };
      });
    }
  },

  setSort: (column) => {
    set((state) =>
      state.sortColumn === column
        ? { sortDirection: state.sortDirection === 'asc' ? 'desc' : 'asc' }
        : { sortColumn: column, sortDirection: 'desc' },
    );
  },

  setPage: (page) => {
    set({ page });
    get().fetchStrategies();
  },

  setStatusFilter: (status) => {
    set({ statusFilter: status, page: 1 });
    get().fetchStrategies();
  },

  setSearchQuery: (query) => {
    set({ searchQuery: query });
    // Debounce would be nice here, but for simplicity just fetch
    get().fetchStrategies();
  },

  deleteStrategy: async (id) => {
    set({ loading: true, error: null });
    try {
      const context = getTenantContext();
      await strategyClient.deleteStrategy({ context, strategyId: id });
      // Remove from local state
      set((state) => {
        const details = { ...state.details };
        delete details[id];
        return {
          strategies: state.strategies.filter((s) => s.id !== id),
          total: state.total - 1,
          details,
          loading: false,
        };
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete strategy',
        loading: false,
      });
    }
  },

  activateStrategy: async (id) => {
    try {
      const context = getTenantContext();
      const response = await strategyClient.updateStrategyStatus({
        context,
        strategyId: id,
        status: StrategyStatus.ACTIVE,
      });
      const updated = response.strategy;
      if (updated) {
        set((state) => ({
          strategies: state.strategies.map((s) => (s.id === id ? { ...s, status: updated.status } : s)),
        }));
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to activate strategy',
      });
    }
  },

  pauseStrategy: async (id) => {
    try {
      const context = getTenantContext();
      const response = await strategyClient.updateStrategyStatus({
        context,
        strategyId: id,
        status: StrategyStatus.PAUSED,
      });
      const updated = response.strategy;
      if (updated) {
        set((state) => ({
          strategies: state.strategies.map((s) => (s.id === id ? { ...s, status: updated.status } : s)),
        }));
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to pause strategy',
      });
    }
  },

  cloneStrategy: async (id, newName) => {
    try {
      const context = getTenantContext();
      // Clone by creating a new strategy based on the existing one
      const getResponse = await strategyClient.getStrategy({ context, strategyId: id });
      const original = getResponse.strategy;
      if (!original) {
        throw new Error('Strategy not found');
      }

      const createResponse = await strategyClient.createStrategy({
        context,
        name: newName ?? `${original.name} (Copy)`,
        description: original.description,
        dslCode: original.dslCode,
        templateId: original.templateId,
        templateParams: original.templateParams,
        symbols: original.symbols,
        timeframe: original.timeframe,
        parameters: original.parameters,
      });

      // Refresh list to include the clone
      get().fetchStrategies();
      return createResponse.strategy?.id ?? null;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to clone strategy',
      });
      return null;
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));
