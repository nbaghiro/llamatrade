// Portfolio Store
// Manages portfolio state including strategy performance data for the portfolio page
//
// Note: After running `make proto`, these types can be replaced with generated proto types:
// import { StrategyPerformanceSummary, ExecutionMode, ExecutionStatus } from '../generated/proto/portfolio_pb';

import { create } from 'zustand';

import { portfolioClient } from '../services/grpc-client';

import { useAuthStore } from './auth';

// Types - these map to proto-generated types after `make proto`
export type ExecutionMode = 'paper' | 'live';
export type ExecutionStatus = 'running' | 'paused' | 'stopped' | 'error';

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
  mode: ExecutionMode;
  status: ExecutionStatus;
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

  // UI State
  selectedPeriod: Period;
  selectedBenchmark: Benchmark;
  expandedStrategyId: string | null;
  visibleStrategyIds: Set<string>;
  hoveredStrategyId: string | null;

  // Async state
  loading: boolean;
  error: string | null;

  // Computed
  totalEquity: number;
  dayPnl: number;
  dayPnlPercent: number;
  totalReturn: number;
  totalReturnPercent: number;

  // Actions
  fetchPortfolio: () => Promise<void>;
  setSelectedPeriod: (period: Period) => void;
  setSelectedBenchmark: (benchmark: Benchmark) => void;
  toggleStrategyExpanded: (id: string) => void;
  toggleStrategyVisibility: (id: string) => void;
  setHoveredStrategy: (id: string | null) => void;
  clearError: () => void;
}

// Color palette for strategies
const STRATEGY_COLORS = [
  '#22c55e', // green
  '#3b82f6', // blue
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#84cc16', // lime
];

// Helper to map proto ExecutionStatus enum to local type
function mapProtoStatus(status: number): ExecutionStatus {
  // Proto enum values: 0=UNSPECIFIED, 1=RUNNING, 2=PAUSED, 3=STOPPED, 4=ERROR
  switch (status) {
    case 1:
      return 'running';
    case 2:
      return 'paused';
    case 3:
      return 'stopped';
    case 4:
      return 'error';
    default:
      return 'stopped';
  }
}

// Demo data generator
function generateDemoEquityCurve(
  _startValue: number,
  returnPercent: number,
  volatility: number,
  days: number
): EquityPoint[] {
  const points: EquityPoint[] = [];
  const now = new Date();
  let value = 0; // Start at 0% return

  for (let i = days; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);

    // Random walk with drift toward final return
    const progress = (days - i) / days;
    const targetReturn = returnPercent * progress;
    const noise = (Math.random() - 0.5) * volatility;
    value = targetReturn + noise;

    points.push({
      timestamp: date.toISOString(),
      value: value * 100, // Store as percentage
    });
  }

  // Ensure last point matches final return
  if (points.length > 0) {
    points[points.length - 1].value = returnPercent * 100;
  }

  return points;
}

function generateBenchmarkData(days: number, returnPercent: number): EquityPoint[] {
  return generateDemoEquityCurve(100000, returnPercent, 0.02, days);
}

// Demo strategies (used as fallback when gRPC is unavailable)
const DEMO_STRATEGIES: StrategyPerformance[] = [
  {
    id: 'exec-1',
    strategyId: 'strat-1',
    name: 'Momentum Alpha',
    mode: 'live',
    status: 'running',
    color: STRATEGY_COLORS[0],
    allocatedCapital: 50000,
    currentValue: 56200,
    positionsCount: 5,
    returns: {
      '1D': 0.008,
      '1W': 0.032,
      '1M': 0.124,
      '3M': 0.185,
      '6M': 0.22,
      '1Y': 0.35,
      'YTD': 0.28,
      'ALL': 0.42,
    },
    startedAt: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000), // 90 days ago
    updatedAt: new Date(),
    equityCurve: generateDemoEquityCurve(50000, 0.124, 0.03, 30),
    positions: [
      {
        symbol: 'NVDA',
        name: 'NVIDIA Corp.',
        qty: 15,
        side: 'long',
        currentPrice: 880,
        avgEntryPrice: 750,
        marketValue: 13200,
        unrealizedPnl: 1950,
        unrealizedPnlPercent: 17.33,
      },
      {
        symbol: 'META',
        name: 'Meta Platforms',
        qty: 20,
        side: 'long',
        currentPrice: 505,
        avgEntryPrice: 480,
        marketValue: 10100,
        unrealizedPnl: 500,
        unrealizedPnlPercent: 5.21,
      },
      {
        symbol: 'AAPL',
        name: 'Apple Inc.',
        qty: 30,
        side: 'long',
        currentPrice: 192,
        avgEntryPrice: 185,
        marketValue: 5760,
        unrealizedPnl: 210,
        unrealizedPnlPercent: 3.78,
      },
    ],
    recentActivity: [
      { id: '1', type: 'buy', symbol: 'NVDA', qty: 5, price: 875, timestamp: new Date(Date.now() - 3600000) },
      { id: '2', type: 'sell', symbol: 'TSLA', qty: 10, price: 205, timestamp: new Date(Date.now() - 86400000) },
    ],
  },
  {
    id: 'exec-2',
    strategyId: 'strat-2',
    name: 'Mean Reversion',
    mode: 'paper',
    status: 'running',
    color: STRATEGY_COLORS[1],
    allocatedCapital: 30000,
    currentValue: 32460,
    positionsCount: 3,
    returns: {
      '1D': 0.005,
      '1W': 0.018,
      '1M': 0.082,
      '3M': 0.12,
      '6M': 0.15,
      '1Y': 0.22,
      'YTD': 0.18,
      'ALL': 0.28,
    },
    startedAt: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000), // 60 days ago
    updatedAt: new Date(),
    equityCurve: generateDemoEquityCurve(30000, 0.082, 0.02, 30),
    positions: [
      {
        symbol: 'JPM',
        name: 'JPMorgan Chase',
        qty: 25,
        side: 'long',
        currentPrice: 198,
        avgEntryPrice: 190,
        marketValue: 4950,
        unrealizedPnl: 200,
        unrealizedPnlPercent: 4.21,
      },
      {
        symbol: 'BAC',
        name: 'Bank of America',
        qty: 100,
        side: 'long',
        currentPrice: 38,
        avgEntryPrice: 36,
        marketValue: 3800,
        unrealizedPnl: 200,
        unrealizedPnlPercent: 5.56,
      },
    ],
    recentActivity: [
      { id: '3', type: 'buy', symbol: 'JPM', qty: 10, price: 195, timestamp: new Date(Date.now() - 7200000) },
    ],
  },
  {
    id: 'exec-3',
    strategyId: 'strat-3',
    name: 'Value Screener',
    mode: 'live',
    status: 'running',
    color: STRATEGY_COLORS[2],
    allocatedCapital: 25000,
    currentValue: 24475,
    positionsCount: 4,
    returns: {
      '1D': -0.003,
      '1W': -0.012,
      '1M': -0.021,
      '3M': 0.05,
      '6M': 0.08,
      '1Y': 0.12,
      'YTD': 0.06,
      'ALL': 0.15,
    },
    startedAt: new Date(Date.now() - 120 * 24 * 60 * 60 * 1000), // 120 days ago
    updatedAt: new Date(),
    equityCurve: generateDemoEquityCurve(25000, -0.021, 0.025, 30),
    positions: [
      {
        symbol: 'INTC',
        name: 'Intel Corp.',
        qty: 50,
        side: 'long',
        currentPrice: 31,
        avgEntryPrice: 34,
        marketValue: 1550,
        unrealizedPnl: -150,
        unrealizedPnlPercent: -8.82,
      },
      {
        symbol: 'WFC',
        name: 'Wells Fargo',
        qty: 40,
        side: 'long',
        currentPrice: 58,
        avgEntryPrice: 55,
        marketValue: 2320,
        unrealizedPnl: 120,
        unrealizedPnlPercent: 5.45,
      },
    ],
    recentActivity: [
      { id: '4', type: 'buy', symbol: 'INTC', qty: 20, price: 32, timestamp: new Date(Date.now() - 172800000) },
    ],
  },
  {
    id: 'exec-4',
    strategyId: 'strat-4',
    name: 'Tech Growth',
    mode: 'paper',
    status: 'paused',
    color: STRATEGY_COLORS[3],
    allocatedCapital: 20000,
    currentValue: 21800,
    positionsCount: 0,
    returns: {
      '1D': 0,
      '1W': 0,
      '1M': 0.09,
      '3M': 0.15,
      '6M': 0.18,
      '1Y': 0.25,
      'YTD': 0.2,
      'ALL': 0.32,
    },
    startedAt: new Date(Date.now() - 180 * 24 * 60 * 60 * 1000), // 180 days ago
    updatedAt: new Date(),
    equityCurve: generateDemoEquityCurve(20000, 0.09, 0.015, 30),
    positions: [],
    recentActivity: [],
  },
];

export const usePortfolioStore = create<PortfolioState>((set) => ({
  // Initial state
  strategies: [],
  benchmarkData: [],

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

  // Actions
  fetchPortfolio: async () => {
    set({ loading: true, error: null });

    try {
      const tenantId = useAuthStore.getState().user?.tenantId;
      let strategies: StrategyPerformance[];

      // Try gRPC call if authenticated
      if (tenantId) {
        try {
          const response = await portfolioClient.listStrategyPerformance({
            context: { tenantId },
            pagination: { page: 1, pageSize: 50 },
          });

          // Transform proto response to local types
          strategies = response.strategies.map((s, i) => ({
            id: s.executionId,
            strategyId: s.strategyId,
            name: s.strategyName,
            mode: (s.mode === 1 ? 'paper' : 'live') as ExecutionMode,
            status: mapProtoStatus(s.status),
            color: s.color || STRATEGY_COLORS[i % STRATEGY_COLORS.length],
            allocatedCapital: parseFloat(s.allocatedCapital?.value || '0'),
            currentValue: parseFloat(s.currentValue?.value || '0'),
            positionsCount: s.positionsCount,
            returns: {
              '1D': parseFloat(s.returns?.return1d?.value || '0'),
              '1W': parseFloat(s.returns?.return1w?.value || '0'),
              '1M': parseFloat(s.returns?.return1m?.value || '0'),
              '3M': parseFloat(s.returns?.return3m?.value || '0'),
              '6M': parseFloat(s.returns?.return6m?.value || '0'),
              '1Y': parseFloat(s.returns?.return1y?.value || '0'),
              'YTD': parseFloat(s.returns?.returnYtd?.value || '0'),
              'ALL': parseFloat(s.returns?.returnAll?.value || '0'),
            },
            startedAt: s.startedAt?.seconds ? new Date(Number(s.startedAt.seconds) * 1000) : null,
            updatedAt: s.updatedAt?.seconds ? new Date(Number(s.updatedAt.seconds) * 1000) : new Date(),
            equityCurve: [], // Loaded separately via getStrategyEquityCurve
            positions: [],   // Loaded separately via getStrategyPerformance
            recentActivity: [],
          }));
        } catch {
          // gRPC unavailable, fall back to demo data
          strategies = DEMO_STRATEGIES;
        }
      } else {
        // Use demo data when not authenticated
        strategies = DEMO_STRATEGIES;
      }

      const visibleIds = new Set(strategies.map((s) => s.id));

      // Calculate totals
      const totalEquity = strategies.reduce((sum, s) => sum + s.currentValue, 0);
      const totalAllocated = strategies.reduce((sum, s) => sum + s.allocatedCapital, 0);
      const totalReturn = totalEquity - totalAllocated;
      const totalReturnPercent = totalAllocated > 0 ? (totalReturn / totalAllocated) * 100 : 0;

      // Day P&L from individual strategies
      const dayPnl = strategies.reduce((sum, s) => {
        return sum + s.currentValue * s.returns['1D'];
      }, 0);
      const dayPnlPercent = totalEquity > 0 ? (dayPnl / (totalEquity - dayPnl)) * 100 : 0;

      // Generate benchmark data
      const benchmarkData = generateBenchmarkData(30, 0.05); // SPY ~5% for 1M

      set({
        strategies,
        benchmarkData,
        visibleStrategyIds: visibleIds,
        totalEquity,
        dayPnl,
        dayPnlPercent,
        totalReturn,
        totalReturnPercent,
        loading: false,
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch portfolio',
        loading: false,
      });
    }
  },

  setSelectedPeriod: (period) => {
    set({ selectedPeriod: period });
    // TODO: Refetch data for new period if needed
  },

  setSelectedBenchmark: (benchmark) => {
    set({ selectedBenchmark: benchmark });
    // TODO: Fetch new benchmark data
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
