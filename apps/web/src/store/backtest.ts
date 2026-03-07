/**
 * Backtest Store
 * Manages backtest state, execution, and progress streaming.
 */

import { Code, ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import {
  BacktestStatus,
  type BacktestRun,
  type BacktestMetrics,
  type BacktestTrade,
  type EquityPoint,
} from '../generated/proto/backtest_pb';
import type { Decimal, Timestamp } from '../generated/proto/common_pb';
import type { Strategy } from '../generated/proto/strategy_pb';
import { backtestClient, strategyClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

// ============================================================================
// Type Conversions
// ============================================================================

/** Convert proto Timestamp to JS Date */
export function toDate(ts: Timestamp | undefined): Date | null {
  if (!ts) return null;
  return new Date(Number(ts.seconds) * 1000 + Math.floor(ts.nanos / 1_000_000));
}

/** Convert JS Date to proto Timestamp */
export function toTimestamp(date: Date): { seconds: bigint; nanos: number } {
  const ms = date.getTime();
  return {
    seconds: BigInt(Math.floor(ms / 1000)),
    nanos: (ms % 1000) * 1_000_000,
  };
}

/** Convert proto Decimal to number */
export function toNumber(decimal: Decimal | undefined): number {
  return decimal?.value ? parseFloat(decimal.value) : 0;
}

/** Convert number to proto Decimal string */
export function toDecimal(value: number): { value: string } {
  return { value: value.toString() };
}

// ============================================================================
// State Types
// ============================================================================

export interface BacktestConfig {
  strategyId: string;
  strategyVersion?: number;
  startDate: string; // ISO date string
  endDate: string; // ISO date string
  initialCapital: number;
  symbols: string[];
  commission: number;
  slippage: number;
  timeframe: string;
}

interface BacktestState {
  // Current backtest being run/viewed
  currentBacktest: BacktestRun | null;

  // History of backtests
  backtests: BacktestRun[];
  totalCount: number;

  // Available strategies for selector
  strategies: Strategy[];
  strategiesLoading: boolean;

  // Form configuration
  config: BacktestConfig;

  // Async state
  loading: boolean;
  streaming: boolean;
  progress: number;
  progressMessage: string;
  error: string | null;

  // Stream abort controller
  abortController: AbortController | null;

  // Actions
  setConfig: (config: Partial<BacktestConfig>) => void;
  runBacktest: () => Promise<string | null>;
  getBacktest: (id: string) => Promise<void>;
  listBacktests: (strategyId?: string, page?: number) => Promise<void>;
  cancelBacktest: (id: string) => Promise<void>;
  streamProgress: (id: string) => Promise<void>;
  stopStreaming: () => void;
  fetchStrategies: () => Promise<void>;
  clearError: () => void;
  reset: () => void;
}

// ============================================================================
// Default Config
// ============================================================================

const defaultConfig: BacktestConfig = {
  strategyId: '',
  strategyVersion: undefined,
  startDate: getDefaultStartDate(),
  endDate: getDefaultEndDate(),
  initialCapital: 100000,
  symbols: [],
  commission: 0.001,
  slippage: 0.001,
  timeframe: '1D',
};

function getDefaultStartDate(): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 1);
  return date.toISOString().split('T')[0];
}

function getDefaultEndDate(): string {
  return new Date().toISOString().split('T')[0];
}

// ============================================================================
// Error Handling
// ============================================================================

function getErrorMessage(error: unknown): string {
  if (error instanceof ConnectError) {
    switch (error.code) {
      case Code.NotFound:
        return 'Strategy or backtest not found';
      case Code.InvalidArgument:
        return error.message || 'Invalid configuration';
      case Code.Unauthenticated:
        return 'Please log in to run backtests';
      case Code.PermissionDenied:
        return 'You do not have permission to run this backtest';
      case Code.ResourceExhausted:
        return 'Rate limit exceeded. Please try again later.';
      case Code.Unavailable:
        return 'Backtest service is temporarily unavailable';
      default:
        return error.message || 'An error occurred';
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}

// ============================================================================
// Store
// ============================================================================

export const useBacktestStore = create<BacktestState>((set, get) => ({
  // Initial state
  currentBacktest: null,
  backtests: [],
  totalCount: 0,
  strategies: [],
  strategiesLoading: false,
  config: { ...defaultConfig },
  loading: false,
  streaming: false,
  progress: 0,
  progressMessage: '',
  error: null,
  abortController: null,

  // Update config
  setConfig: (updates) => {
    set((state) => ({
      config: { ...state.config, ...updates },
    }));
  },

  // Fetch available strategies for dropdown
  fetchStrategies: async () => {
    set({ strategiesLoading: true });

    const context = getTenantContext();
    if (!context) {
      // Not logged in - can't fetch strategies
      set({
        strategies: [],
        strategiesLoading: false,
      });
      return;
    }

    try {
      const response = await strategyClient.listStrategies({
        context,
        pagination: { page: 1, pageSize: 100 },
      });
      set({
        strategies: response.strategies,
        strategiesLoading: false,
      });
    } catch {
      // Don't show a blocking error for strategy fetching
      // The user can still configure other settings and will see validation error on submit
      set({
        strategies: [],
        strategiesLoading: false,
      });
    }
  },

  // Run a new backtest
  runBacktest: async () => {
    const { config } = get();

    // Validation
    if (!config.strategyId) {
      set({ error: 'Please select a strategy' });
      return null;
    }

    const context = getTenantContext();
    if (!context) {
      set({ error: 'Please log in to run backtests' });
      return null;
    }

    const startDate = new Date(config.startDate);
    const endDate = new Date(config.endDate);

    if (endDate <= startDate) {
      set({ error: 'End date must be after start date' });
      return null;
    }

    set({
      loading: true,
      error: null,
      progress: 0,
      progressMessage: 'Starting backtest...',
    });

    try {
      const response = await backtestClient.runBacktest({
        context,
        config: {
          strategyId: config.strategyId,
          strategyVersion: config.strategyVersion ?? 0,
          startDate: toTimestamp(startDate),
          endDate: toTimestamp(endDate),
          initialCapital: toDecimal(config.initialCapital),
          symbols: config.symbols,
          commission: toDecimal(config.commission),
          slippagePercent: toDecimal(config.slippage),
          timeframe: config.timeframe,
          allowShorting: false,
          useAdjustedPrices: true,
          parameters: {},
        },
      });

      const backtest = response.backtest;
      if (!backtest) {
        throw new Error('Failed to start backtest');
      }

      set({
        currentBacktest: backtest,
        loading: false,
      });

      // Start streaming progress
      get().streamProgress(backtest.id);

      return backtest.id;
    } catch (error) {
      set({
        error: getErrorMessage(error),
        loading: false,
      });
      return null;
    }
  },

  // Get backtest by ID
  getBacktest: async (id) => {
    const context = getTenantContext();
    if (!context) {
      set({ error: 'Please log in to view backtests', loading: false });
      return;
    }

    set({ loading: true, error: null });
    try {
      const response = await backtestClient.getBacktest({ context, backtestId: id });
      set({
        currentBacktest: response.backtest ?? null,
        loading: false,
      });
    } catch (error) {
      set({
        error: getErrorMessage(error),
        loading: false,
      });
    }
  },

  // List backtests
  listBacktests: async (strategyId, page = 1) => {
    const context = getTenantContext();
    if (!context) {
      set({ backtests: [], loading: false });
      return;
    }

    set({ loading: true, error: null });
    try {
      const response = await backtestClient.listBacktests({
        context,
        strategyId: strategyId ?? '',
        pagination: { page, pageSize: 20 },
      });
      set({
        backtests: response.backtests,
        totalCount: response.pagination?.totalItems ?? response.backtests.length,
        loading: false,
      });
    } catch (error) {
      set({
        error: getErrorMessage(error),
        loading: false,
      });
    }
  },

  // Cancel a running backtest
  cancelBacktest: async (id) => {
    const context = getTenantContext();
    if (!context) return;

    try {
      const response = await backtestClient.cancelBacktest({ context, backtestId: id });
      const backtest = response.backtest;
      if (backtest) {
        set((state) => ({
          currentBacktest:
            state.currentBacktest?.id === id ? backtest : state.currentBacktest,
        }));
      }
      // Stop streaming
      get().stopStreaming();
    } catch (error) {
      set({ error: getErrorMessage(error) });
    }
  },

  // Stream progress updates
  streamProgress: async (backtestId) => {
    const context = getTenantContext();
    if (!context) return;

    // Stop any existing stream
    get().stopStreaming();

    const abortController = new AbortController();
    set({
      streaming: true,
      abortController,
      progress: 0,
      progressMessage: 'Initializing...',
    });

    try {
      const stream = backtestClient.streamBacktestProgress(
        { context, backtestId },
        { signal: abortController.signal }
      );

      for await (const update of stream) {
        // Check if we should stop
        if (abortController.signal.aborted) {
          break;
        }

        const current = get().currentBacktest;
        set({
          progress: update.progressPercent,
          progressMessage: update.message || getProgressPhaseMessage(update.progressPercent),
          ...(current && {
            currentBacktest: {
              ...current,
              status: update.status,
              progressPercent: update.progressPercent,
              currentDate: update.currentDate,
            } as BacktestRun,
          }),
        });

        // If completed or failed, fetch full results
        if (
          update.status === BacktestStatus.COMPLETED ||
          update.status === BacktestStatus.FAILED ||
          update.status === BacktestStatus.CANCELLED
        ) {
          await get().getBacktest(backtestId);
          break;
        }
      }
    } catch (error) {
      // Don't set error if it was just cancelled
      if (!abortController.signal.aborted) {
        // Fetch final state on error
        await get().getBacktest(backtestId);
      }
    } finally {
      set({ streaming: false, abortController: null });
    }
  },

  // Stop streaming
  stopStreaming: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ streaming: false, abortController: null });
    }
  },

  // Clear error
  clearError: () => {
    set({ error: null });
  },

  // Reset store
  reset: () => {
    get().stopStreaming();
    set({
      currentBacktest: null,
      backtests: [],
      totalCount: 0,
      config: { ...defaultConfig },
      loading: false,
      streaming: false,
      progress: 0,
      progressMessage: '',
      error: null,
    });
  },
}));

// ============================================================================
// Helpers
// ============================================================================

function getProgressPhaseMessage(percent: number): string {
  if (percent < 5) return 'Loading strategy...';
  if (percent < 15) return 'Fetching market data...';
  if (percent < 90) return 'Running simulation...';
  if (percent < 100) return 'Calculating metrics...';
  return 'Complete';
}

// ============================================================================
// Derived Data Helpers
// ============================================================================

/** Extract and format metrics for display */
export function formatMetrics(metrics: BacktestMetrics | undefined): Record<string, string> {
  if (!metrics) return {};

  return {
    totalReturn: formatPercent(toNumber(metrics.totalReturn)),
    annualizedReturn: formatPercent(toNumber(metrics.annualizedReturn)),
    sharpeRatio: toNumber(metrics.sharpeRatio).toFixed(2),
    sortinoRatio: toNumber(metrics.sortinoRatio).toFixed(2),
    maxDrawdown: formatPercent(toNumber(metrics.maxDrawdown)),
    volatility: formatPercent(toNumber(metrics.volatility)),
    winRate: formatPercent(toNumber(metrics.winRate)),
    profitFactor: toNumber(metrics.profitFactor).toFixed(2),
    totalTrades: metrics.totalTrades.toString(),
    winningTrades: metrics.winningTrades.toString(),
    losingTrades: metrics.losingTrades.toString(),
    averageWin: formatCurrency(toNumber(metrics.averageWin)),
    averageLoss: formatCurrency(toNumber(metrics.averageLoss)),
    startingCapital: formatCurrency(toNumber(metrics.startingCapital)),
    endingCapital: formatCurrency(toNumber(metrics.endingCapital)),
    peakCapital: formatCurrency(toNumber(metrics.peakCapital)),
    totalCommission: formatCurrency(toNumber(metrics.totalCommission)),
    alpha: toNumber(metrics.alpha).toFixed(3),
    beta: toNumber(metrics.beta).toFixed(3),
  };
}

/** Format equity curve for charting */
export function formatEquityCurve(
  points: EquityPoint[]
): Array<{ date: Date; equity: number; drawdown: number; dailyReturn: number }> {
  return points.map((p) => ({
    date: toDate(p.timestamp) ?? new Date(),
    equity: toNumber(p.equity),
    drawdown: toNumber(p.drawdown),
    dailyReturn: toNumber(p.dailyReturn),
  }));
}

/** Format trades for table display */
export function formatTrades(
  trades: BacktestTrade[]
): Array<{
  symbol: string;
  side: string;
  quantity: number;
  entryPrice: number;
  exitPrice: number;
  entryTime: Date | null;
  exitTime: Date | null;
  pnl: number;
  pnlPercent: number;
  commission: number;
  holdingPeriod: number;
}> {
  return trades.map((t) => ({
    symbol: t.symbol,
    side: t.side === 1 ? 'BUY' : 'SELL',
    quantity: toNumber(t.quantity),
    entryPrice: toNumber(t.entryPrice),
    exitPrice: toNumber(t.exitPrice),
    entryTime: toDate(t.entryTime),
    exitTime: toDate(t.exitTime),
    pnl: toNumber(t.pnl),
    pnlPercent: toNumber(t.pnlPercent),
    commission: toNumber(t.commission),
    holdingPeriod: t.holdingPeriodBars,
  }));
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}
