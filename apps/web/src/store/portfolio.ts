// Portfolio store: strategy performance data for the portfolio page

import { create } from 'zustand';

import {
  ExecutionMode,
  ExecutionStatus,
  type Decimal,
  type Timestamp,
} from '../generated/proto/common_pb';
import { MarketStatus } from '../generated/proto/market_data_pb';
import type {
  GetStrategyEquityCurveResponse,
  StrategyEquityPoint,
} from '../generated/proto/portfolio_pb';
import { PositionSide, type Position as ProtoPosition } from '../generated/proto/trading_pb';
import { marketDataClient, portfolioClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

export { ExecutionMode, ExecutionStatus, MarketStatus };

export interface Position {
  symbol: string;
  name: string;
  qty: number;
  side: 'long' | 'short';
  currentPrice: number;
  avgEntryPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
}

export interface Activity {
  id: string;
  type: 'buy' | 'sell';
  symbol: string;
  qty: number;
  price: number;
  timestamp: Date;
}

export interface EquityPoint {
  timestamp: string;
  value: number;
  returnPercent?: number;
  drawdown?: number;
  benchmarkValue?: number;
}

export type Period = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | 'YTD' | 'ALL';

export interface PeriodReturns {
  '1D': number;
  '1W': number;
  '1M': number;
  '3M': number;
  '6M': number;
  '1Y': number;
  'YTD': number;
  'ALL': number;
}

export interface StrategyPerformance {
  id: string;         // execution_id
  strategyId: string; // strategy_id
  name: string;
  mode: ExecutionMode;      // Proto enum value
  status: ExecutionStatus;  // Proto enum value
  color: string;

  // Aggregates
  allocatedCapital: number;
  currentValue: number;
  positionsCount: number;

  // Returns for each period (as decimal, e.g., 0.12 = 12%)
  returns: PeriodReturns;

  // Timestamps
  startedAt: Date | null;
  updatedAt: Date;

  // Time series for chart (normalized to % return)
  equityCurve: EquityPoint[];

  // For expanded view
  positions: Position[];
  recentActivity: Activity[];
}

export type Benchmark = 'none' | 'SPY' | 'QQQ' | 'IWM' | 'DIA';

interface PortfolioState {
  // Data
  strategies: StrategyPerformance[];
  benchmarkData: EquityPoint[];
  portfolioCurve: EquityPoint[]; // blended account equity line (the hero series)

  // UI State
  selectedPeriod: Period;
  selectedBenchmark: Benchmark;
  expandedStrategyId: string | null;
  visibleStrategyIds: Set<string>;
  hoveredStrategyId: string | null;

  // Async state
  loading: boolean;
  error: string | null;

  // Account-level computed values
  totalEquity: number;
  dayPnl: number;
  dayPnlPercent: number;
  totalReturn: number;
  totalReturnPercent: number;
  freeCash: number;
  freeCashPercent: number;
  deployedValue: number;
  liveStrategiesCount: number;
  openPositionsCount: number;
  accountMode: ExecutionMode;

  // Market clock
  marketStatus: MarketStatus | null;
  marketNextOpen: Date | null;
  marketNextClose: Date | null;

  // Actions
  fetchPortfolio: () => Promise<void>;
  fetchMarketStatus: () => Promise<void>;
  setSelectedPeriod: (period: Period) => void;
  setSelectedBenchmark: (benchmark: Benchmark) => void;
  toggleStrategyExpanded: (id: string) => void;
  toggleStrategyVisibility: (id: string) => void;
  setHoveredStrategy: (id: string | null) => void;
  clearError: () => void;
}

// Categorical series palette (Monolith tokens), assigned per strategy slot; colorblind-safe (validated with the dataviz skill).
const STRATEGY_COLORS = [
  '#0f7a34', // green  — Monolith success
  '#1a1aff', // blue   — Monolith info
  '#ff4d1c', // orange — Monolith signal accent
  '#c81e1e', // red    — Monolith danger
  '#6b2fb3', // violet — overflow
  '#0e8ba0', // cyan   — overflow
];

function mapProtoStatus(status: number): ExecutionStatus {
  // Proto enum values: 0=UNSPECIFIED, 1=PENDING, 2=RUNNING, 3=PAUSED, 4=STOPPED, 5=ERROR
  switch (status) {
    case ExecutionStatus.RUNNING:
      return ExecutionStatus.RUNNING;
    case ExecutionStatus.PAUSED:
      return ExecutionStatus.PAUSED;
    case ExecutionStatus.STOPPED:
      return ExecutionStatus.STOPPED;
    case ExecutionStatus.ERROR:
      return ExecutionStatus.ERROR;
    case ExecutionStatus.PENDING:
      return ExecutionStatus.PENDING;
    default:
      return ExecutionStatus.STOPPED;
  }
}

// Proto → local conversion helpers

function decimalToNumber(d: Decimal | undefined): number {
  return d?.value ? parseFloat(d.value) : 0;
}

function timestampToISO(ts: Timestamp | undefined): string {
  if (!ts?.seconds) return new Date().toISOString();
  return new Date(Number(ts.seconds) * 1000).toISOString();
}

function mapProtoPosition(p: ProtoPosition): Position {
  return {
    symbol: p.symbol,
    name: '', // Proto Position carries no asset-class label — left blank.
    qty: decimalToNumber(p.quantity),
    side: p.side === PositionSide.SHORT ? 'short' : 'long',
    currentPrice: decimalToNumber(p.currentPrice),
    avgEntryPrice: decimalToNumber(p.averageEntryPrice),
    marketValue: decimalToNumber(p.marketValue),
    unrealizedPnl: decimalToNumber(p.unrealizedPnl),
    unrealizedPnlPercent: decimalToNumber(p.unrealizedPnlPercent),
  };
}

/**
 * Convert a strategy equity curve into the chart's `EquityPoint[]`. The chart
 * plots `value` as a cumulative-return percentage, so we derive it from the
 * real absolute `equity` series (normalized against the first point) rather
 * than the backend `return_percent` field, which is not always populated.
 */
function normalizeEquityCurve(points: StrategyEquityPoint[]): EquityPoint[] {
  if (points.length === 0) return [];
  const base = decimalToNumber(points[0].equity);
  return points.map((p) => {
    const equity = decimalToNumber(p.equity);
    return {
      timestamp: timestampToISO(p.timestamp),
      value: base !== 0 ? (equity / base - 1) * 100 : 0,
      drawdown: decimalToNumber(p.drawdown),
      benchmarkValue: p.benchmarkValue ? decimalToNumber(p.benchmarkValue) : undefined,
    };
  });
}

/**
 * Normalize a benchmark equity series (absolute values) into a percentage
 * return series comparable to the strategy lines.
 */
function normalizeBenchmark(points: StrategyEquityPoint[]): EquityPoint[] {
  if (points.length === 0) return [];
  const base = decimalToNumber(points[0].equity);
  return points.map((p) => ({
    timestamp: timestampToISO(p.timestamp),
    value: base !== 0 ? (decimalToNumber(p.equity) / base - 1) * 100 : 0,
  }));
}

/**
 * Blend the per-strategy absolute-equity curves into one account-level return
 * series. Series are right-anchored to "now": a strategy with less history
 * contributes its capital-at-cost for the periods before it began, so the
 * portfolio line reflects the whole book rather than only the longest-lived leg.
 */
function buildPortfolioCurve(
  rawCurves: (GetStrategyEquityCurveResponse | null)[],
  strategies: StrategyPerformance[]
): EquityPoint[] {
  const series: { equity: number[]; timestamps: string[]; baseline: number }[] = [];
  rawCurves.forEach((curve, i) => {
    const pts = curve?.equityCurve;
    if (!pts || pts.length === 0) return;
    const equity = pts.map((p) => decimalToNumber(p.equity));
    series.push({
      equity,
      timestamps: pts.map((p) => timestampToISO(p.timestamp)),
      baseline: strategies[i].allocatedCapital || equity[0],
    });
  });
  if (series.length === 0) return [];

  const maxLen = Math.max(...series.map((s) => s.equity.length));
  const totalBaseline = series.reduce((sum, s) => sum + s.baseline, 0);
  const longest = series.find((s) => s.equity.length === maxLen) ?? series[0];

  const out: EquityPoint[] = [];
  for (let j = 0; j < maxLen; j++) {
    let sum = 0;
    for (const s of series) {
      const pos = s.equity.length - maxLen + j;
      sum += pos >= 0 ? s.equity[pos] : s.baseline;
    }
    out.push({
      timestamp: longest.timestamps[j] ?? new Date().toISOString(),
      value: totalBaseline > 0 ? (sum / totalBaseline - 1) * 100 : 0,
    });
  }
  return out;
}

const EMPTY_PORTFOLIO = {
  strategies: [] as StrategyPerformance[],
  benchmarkData: [] as EquityPoint[],
  portfolioCurve: [] as EquityPoint[],
  visibleStrategyIds: new Set<string>(),
  totalEquity: 0,
  dayPnl: 0,
  dayPnlPercent: 0,
  totalReturn: 0,
  totalReturnPercent: 0,
  freeCash: 0,
  freeCashPercent: 0,
  deployedValue: 0,
  liveStrategiesCount: 0,
  openPositionsCount: 0,
  accountMode: ExecutionMode.PAPER,
};

export const usePortfolioStore = create<PortfolioState>((set, get) => ({
  // Initial state
  strategies: [],
  benchmarkData: [],
  portfolioCurve: [],

  selectedPeriod: '1M',
  selectedBenchmark: 'SPY',
  expandedStrategyId: null,
  visibleStrategyIds: new Set(),
  hoveredStrategyId: null,

  loading: false,
  error: null,

  // Computed values
  totalEquity: 0,
  dayPnl: 0,
  dayPnlPercent: 0,
  totalReturn: 0,
  totalReturnPercent: 0,
  freeCash: 0,
  freeCashPercent: 0,
  deployedValue: 0,
  liveStrategiesCount: 0,
  openPositionsCount: 0,
  accountMode: ExecutionMode.PAPER,

  marketStatus: null,
  marketNextOpen: null,
  marketNextClose: null,

  // Actions
  fetchPortfolio: async () => {
    set({ loading: true, error: null });

    const context = getTenantContext();

    // Not authenticated → clean empty state. Never fall back to mock data.
    if (!context) {
      set({ ...EMPTY_PORTFOLIO, loading: false, error: null });
      return;
    }

    try {
      const { selectedBenchmark } = get();
      const benchmarkSymbol = selectedBenchmark === 'none' ? '' : selectedBenchmark;

      const response = await portfolioClient.listStrategyPerformance({
        context,
        pagination: { page: 1, pageSize: 50 },
      });

      // Map summaries → local StrategyPerformance. Period returns are stored as
      // decimals (0.12 = 12%); the backend sends percentages, so divide by 100.
      const strategies: StrategyPerformance[] = response.strategies.map((s, i) => ({
        id: s.executionId,
        strategyId: s.strategyId,
        name: s.strategyName,
        mode: s.mode === ExecutionMode.LIVE ? ExecutionMode.LIVE : ExecutionMode.PAPER,
        status: mapProtoStatus(s.status),
        color: s.color || STRATEGY_COLORS[i % STRATEGY_COLORS.length],
        allocatedCapital: decimalToNumber(s.allocatedCapital),
        currentValue: decimalToNumber(s.currentValue),
        positionsCount: s.positionsCount,
        returns: {
          '1D': decimalToNumber(s.returns?.return1d) / 100,
          '1W': decimalToNumber(s.returns?.return1w) / 100,
          '1M': decimalToNumber(s.returns?.return1m) / 100,
          '3M': decimalToNumber(s.returns?.return3m) / 100,
          '6M': decimalToNumber(s.returns?.return6m) / 100,
          '1Y': decimalToNumber(s.returns?.return1y) / 100,
          'YTD': decimalToNumber(s.returns?.returnYtd) / 100,
          'ALL': decimalToNumber(s.returns?.returnAll) / 100,
        },
        startedAt: s.startedAt?.seconds ? new Date(Number(s.startedAt.seconds) * 1000) : null,
        updatedAt: s.updatedAt?.seconds ? new Date(Number(s.updatedAt.seconds) * 1000) : new Date(),
        equityCurve: [],
        positions: [],
        recentActivity: [],
      }));

      // Fetch account summary + per-strategy curves + positions in parallel; each tolerates null so one failure can't blank the page.
      const [portfolioList, curves, perfs] = await Promise.all([
        portfolioClient.listPortfolios({ context, pagination: { page: 1, pageSize: 1 } }).catch(() => null),
        Promise.all(
          strategies.map((s) =>
            portfolioClient
              .getStrategyEquityCurve({
                context,
                executionId: s.id,
                benchmarkSymbol,
                sampleIntervalMinutes: 0,
              })
              .catch(() => null)
          )
        ),
        Promise.all(
          strategies.map((s) =>
            portfolioClient
              .getStrategyPerformance({ context, executionId: s.id })
              .catch(() => null)
          )
        ),
      ]);

      let benchmarkData: EquityPoint[] = [];
      curves.forEach((curve, i) => {
        if (!curve) return;
        strategies[i].equityCurve = normalizeEquityCurve(curve.equityCurve);

        // Shared benchmark line from the first strategy with benchmark data (dedicated series, else per-point benchmark_value).
        if (benchmarkData.length === 0 && benchmarkSymbol) {
          if (curve.benchmark?.equityCurve?.length) {
            benchmarkData = normalizeBenchmark(curve.benchmark.equityCurve);
          } else {
            const withBench = curve.equityCurve.filter((p) => p.benchmarkValue);
            if (withBench.length > 0) {
              const base = decimalToNumber(withBench[0].benchmarkValue);
              benchmarkData = withBench.map((p) => ({
                timestamp: timestampToISO(p.timestamp),
                value: base !== 0 ? (decimalToNumber(p.benchmarkValue) / base - 1) * 100 : 0,
              }));
            }
          }
        }
      });

      // Attach real open positions per strategy for the expandable detail rows.
      perfs.forEach((perf, i) => {
        if (!perf) return;
        strategies[i].positions = perf.positions.map(mapProtoPosition);
        if (perf.positions.length > 0) {
          strategies[i].positionsCount = perf.positions.length;
        }
      });

      const portfolioCurve = buildPortfolioCurve(curves, strategies);
      const visibleIds = new Set(strategies.map((s) => s.id));

      // Strategy book: market value (positions + sleeve cash) and cost basis.
      const totalStrategyValue = strategies.reduce((sum, s) => sum + s.currentValue, 0);
      const totalAllocated = strategies.reduce((sum, s) => sum + s.allocatedCapital, 0);
      const hasStrategies = strategies.length > 0;

      // Prefer the real account summary; otherwise derive from the strategy book.
      const summary = portfolioList?.portfolios[0];
      const summaryTotal = summary ? decimalToNumber(summary.totalValue) : 0;
      const summaryCash = summary ? decimalToNumber(summary.cashBalance) : 0;
      const summaryPositions = summary ? decimalToNumber(summary.positionsValue) : 0;

      const totalEquity = summaryTotal || totalStrategyValue + summaryCash;
      const freeCash = summaryCash || Math.max(0, totalEquity - totalStrategyValue);
      const freeCashPercent = totalEquity > 0 ? (freeCash / totalEquity) * 100 : 0;

      // Deployed = positions marked to market, NOT Σ sleeve equity (which double-counts sleeve cash free cash already covers).
      const deployedValue = summaryPositions || Math.max(0, totalEquity - freeCash);

      // Total return + Day P&L share one basis with the rows (Σ current − Σ allocated) so the header equals the row sum.
      const derivedReturn = totalStrategyValue - totalAllocated;
      const derivedDayPnl = strategies.reduce((sum, s) => sum + s.currentValue * s.returns['1D'], 0);
      const summaryReturn = summary ? decimalToNumber(summary.totalReturn) : 0;
      const summaryReturnPct = summary ? decimalToNumber(summary.totalReturnPercent) : 0;
      const summaryDayPct = summary ? decimalToNumber(summary.dayReturnPercent) : 0;

      const totalReturn = hasStrategies ? derivedReturn : summaryReturn;
      const totalReturnPercent = hasStrategies
        ? totalAllocated > 0
          ? (derivedReturn / totalAllocated) * 100
          : 0
        : summaryReturnPct;
      const dayPnl = hasStrategies ? derivedDayPnl : summary ? decimalToNumber(summary.dayReturn) : 0;
      const dayPnlPercent = hasStrategies
        ? totalEquity - dayPnl > 0
          ? (dayPnl / (totalEquity - dayPnl)) * 100
          : 0
        : summaryDayPct;

      const liveStrategiesCount = strategies.filter(
        (s) => s.status === ExecutionStatus.RUNNING
      ).length;
      const openPositionsCount = strategies.reduce((sum, s) => sum + s.positionsCount, 0);
      const accountMode = strategies.some((s) => s.mode === ExecutionMode.LIVE)
        ? ExecutionMode.LIVE
        : ExecutionMode.PAPER;

      set({
        strategies,
        benchmarkData,
        portfolioCurve,
        visibleStrategyIds: visibleIds,
        totalEquity,
        dayPnl,
        dayPnlPercent,
        totalReturn,
        totalReturnPercent,
        freeCash,
        freeCashPercent,
        deployedValue,
        liveStrategiesCount,
        openPositionsCount,
        accountMode,
        loading: false,
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch portfolio',
        loading: false,
      });
    }
  },

  // Market clock is best-effort and never gates the page render. On failure the
  // header falls back to deriving open/closed from the browser's ET clock.
  fetchMarketStatus: async () => {
    try {
      const res = await marketDataClient.getMarketStatus({});
      set({
        marketStatus: res.status,
        marketNextOpen: res.nextOpen?.seconds ? new Date(Number(res.nextOpen.seconds) * 1000) : null,
        marketNextClose: res.nextClose?.seconds
          ? new Date(Number(res.nextClose.seconds) * 1000)
          : null,
      });
    } catch {
      set({ marketStatus: null, marketNextOpen: null, marketNextClose: null });
    }
  },

  setSelectedPeriod: (period) => {
    set({ selectedPeriod: period });
    // Period is applied client-side over the full equity curve.
  },

  setSelectedBenchmark: (benchmark) => {
    set({ selectedBenchmark: benchmark });
    // The benchmark series is fetched alongside the equity curves, so refetch.
    get().fetchPortfolio();
  },

  toggleStrategyExpanded: (id) => {
    set((state) => ({
      expandedStrategyId: state.expandedStrategyId === id ? null : id,
    }));
  },

  toggleStrategyVisibility: (id) => {
    set((state) => {
      const newVisible = new Set(state.visibleStrategyIds);
      if (newVisible.has(id)) {
        newVisible.delete(id);
      } else {
        newVisible.add(id);
      }
      return { visibleStrategyIds: newVisible };
    });
  },

  setHoveredStrategy: (id) => {
    set({ hoveredStrategyId: id });
  },

  clearError: () => {
    set({ error: null });
  },
}));
