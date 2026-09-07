/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const rpc = vi.hoisted(() => ({
  listStrategyPerformance: vi.fn(),
  listPortfolios: vi.fn(),
  getStrategyEquityCurve: vi.fn(),
  getStrategyPerformance: vi.fn(),
  listTransactions: vi.fn(),
  getPositions: vi.fn(),
  getMarketStatus: vi.fn(),
}));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  portfolioClient: {
    listStrategyPerformance: rpc.listStrategyPerformance,
    listPortfolios: rpc.listPortfolios,
    getStrategyEquityCurve: rpc.getStrategyEquityCurve,
    getStrategyPerformance: rpc.getStrategyPerformance,
    listTransactions: rpc.listTransactions,
    getPositions: rpc.getPositions,
  },
  marketDataClient: { getMarketStatus: rpc.getMarketStatus },
  getTenantContext: () => tenantContext,
}));

import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';

const dec = (v: number | string) => ({ value: String(v) });
const ts = (seconds: number) => ({ seconds: BigInt(seconds) });

function perf(over: Record<string, unknown> = {}) {
  return {
    executionId: 'exec-1',
    strategyId: 'strat-1',
    strategyName: 'Momentum',
    mode: ExecutionMode.PAPER,
    status: ExecutionStatus.RUNNING,
    color: '',
    allocatedCapital: dec(1000),
    currentValue: dec(1000),
    positionsCount: 1,
    returns: undefined,
    ...over,
  };
}

function curve(values: number[]) {
  return {
    equityCurve: values.map((v, i) => ({
      equity: dec(v),
      timestamp: ts(1000 + i * 60),
      drawdown: dec(0),
    })),
    benchmark: undefined,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  usePortfolioStore.setState({
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
    totalEquity: 0,
    deployedValue: 0,
    liveStrategiesCount: 0,
    openPositionsCount: 0,
  });
  rpc.listStrategyPerformance.mockResolvedValue({ strategies: [] });
  rpc.listPortfolios.mockResolvedValue({ portfolios: [] });
  rpc.getStrategyEquityCurve.mockResolvedValue(curve([]));
  // proto3 always initializes repeated fields, so positions is never absent.
  rpc.getStrategyPerformance.mockResolvedValue({ positions: [] });
  rpc.listTransactions.mockResolvedValue({ transactions: [] });
  rpc.getPositions.mockResolvedValue({ positions: [] });
  rpc.getMarketStatus.mockResolvedValue({});
});

describe('fetchPortfolio', () => {
  it('resets to a clean empty state when signed out, never to mock data', async () => {
    tenantContext = undefined;
    usePortfolioStore.setState({ totalEquity: 500, strategies: [perf()] as never });

    await usePortfolioStore.getState().fetchPortfolio();

    const state = usePortfolioStore.getState();
    expect(state.strategies).toEqual([]);
    expect(state.totalEquity).toBe(0);
    expect(state.error).toBeNull();
    expect(rpc.listStrategyPerformance).not.toHaveBeenCalled();
  });

  it('maps deployments and converts percentage returns to decimals', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf({ returns: { return1m: dec(12), return1d: dec(1) } })],
    });

    await usePortfolioStore.getState().fetchPortfolio();

    const strategy = usePortfolioStore.getState().strategies[0];
    expect(strategy.id).toBe('exec-1');
    expect(strategy.name).toBe('Momentum');
    expect(strategy.color).toBeTruthy(); // falls back to the shared palette
    expect(strategy.returns['1M']).toBeCloseTo(0.12);
  });

  it('requests no benchmark when the selection is none', async () => {
    usePortfolioStore.setState({ selectedBenchmark: 'none' });
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });

    await usePortfolioStore.getState().fetchPortfolio();

    expect(rpc.getStrategyEquityCurve.mock.calls[0][0].benchmarkSymbol).toBe('');
  });

  it('normalizes each equity curve to a percentage series', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([200, 220, 180]));

    await usePortfolioStore.getState().fetchPortfolio();

    const values = usePortfolioStore.getState().strategies[0].equityCurve.map((p) => p.value);
    expect(values[0]).toBeCloseTo(0);
    expect(values[1]).toBeCloseTo(10);
    expect(values[2]).toBeCloseTo(-10);
  });

  it('right-anchors a short leg so the account line covers the whole book', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [
        perf({ executionId: 'e1', allocatedCapital: dec(100) }),
        perf({ executionId: 'e2', allocatedCapital: dec(100) }),
      ],
    });
    rpc.getStrategyEquityCurve
      .mockResolvedValueOnce(curve([100, 100, 120]))
      .mockResolvedValueOnce(curve([100, 100]));

    await usePortfolioStore.getState().fetchPortfolio();

    const values = usePortfolioStore.getState().portfolioCurve.map((p) => p.value);
    expect(values).toHaveLength(3);
    expect(values[0]).toBeCloseTo(0);
    expect(values[2]).toBeCloseTo(10);
  });

  it('counts live deployments and open positions', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [
        perf({ executionId: 'e1', status: ExecutionStatus.RUNNING, positionsCount: 2 }),
        perf({ executionId: 'e2', status: ExecutionStatus.PAUSED, positionsCount: 1 }),
      ],
    });

    await usePortfolioStore.getState().fetchPortfolio();

    const state = usePortfolioStore.getState();
    expect(state.liveStrategiesCount).toBe(1);
    expect(state.openPositionsCount).toBe(3);
  });

  it('maps an unrecognised execution status to stopped rather than running', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf({ status: 99 })] });

    await usePortfolioStore.getState().fetchPortfolio();

    // Defaulting an unknown status to running would show a dead strategy as live.
    expect(usePortfolioStore.getState().strategies[0].status).toBe(ExecutionStatus.STOPPED);
    expect(usePortfolioStore.getState().liveStrategiesCount).toBe(0);
  });

  it('records an error and stops loading when the driving read fails', async () => {
    rpc.listStrategyPerformance.mockRejectedValue(new Error('portfolio down'));

    await usePortfolioStore.getState().fetchPortfolio();

    const state = usePortfolioStore.getState();
    expect(state.error).toBeTruthy();
    expect(state.loading).toBe(false);
  });
});

describe('chart controls', () => {
  it('setSelectedPeriod and setSelectedBenchmark record the choice', () => {
    usePortfolioStore.getState().setSelectedPeriod('1Y');
    usePortfolioStore.getState().setSelectedBenchmark('QQQ');

    expect(usePortfolioStore.getState().selectedPeriod).toBe('1Y');
    expect(usePortfolioStore.getState().selectedBenchmark).toBe('QQQ');
  });

  it('toggleStrategyExpanded opens one row and collapses on a repeat', () => {
    usePortfolioStore.getState().toggleStrategyExpanded('a');
    expect(usePortfolioStore.getState().expandedStrategyId).toBe('a');

    usePortfolioStore.getState().toggleStrategyExpanded('b');
    expect(usePortfolioStore.getState().expandedStrategyId).toBe('b');

    usePortfolioStore.getState().toggleStrategyExpanded('b');
    expect(usePortfolioStore.getState().expandedStrategyId).toBeNull();
  });

  it('toggleStrategyVisibility adds then removes a series', () => {
    usePortfolioStore.getState().toggleStrategyVisibility('a');
    expect(usePortfolioStore.getState().visibleStrategyIds.has('a')).toBe(true);

    usePortfolioStore.getState().toggleStrategyVisibility('a');
    expect(usePortfolioStore.getState().visibleStrategyIds.has('a')).toBe(false);
  });

  it('toggleStrategyVisibility replaces the set so subscribers re-render', () => {
    const before = usePortfolioStore.getState().visibleStrategyIds;

    usePortfolioStore.getState().toggleStrategyVisibility('a');

    // Mutating the Set in place would not notify zustand subscribers.
    expect(usePortfolioStore.getState().visibleStrategyIds).not.toBe(before);
  });

  it('setHoveredStrategy records and clears the hover target', () => {
    usePortfolioStore.getState().setHoveredStrategy('a');
    expect(usePortfolioStore.getState().hoveredStrategyId).toBe('a');

    usePortfolioStore.getState().setHoveredStrategy(null);
    expect(usePortfolioStore.getState().hoveredStrategyId).toBeNull();
  });

  it('clearError resets the message', () => {
    usePortfolioStore.setState({ error: 'boom' });

    usePortfolioStore.getState().clearError();

    expect(usePortfolioStore.getState().error).toBeNull();
  });
});
