/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const rpc = vi.hoisted(() => ({
  listStrategyPerformance: vi.fn(),
  listPortfolios: vi.fn(),
  getStrategyEquityCurve: vi.fn(),
  listTransactions: vi.fn(),
  listStrategies: vi.fn(),
  listBacktests: vi.fn(),
  getBacktest: vi.fn(),
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
    listTransactions: rpc.listTransactions,
  },
  strategyClient: { listStrategies: rpc.listStrategies },
  backtestClient: { listBacktests: rpc.listBacktests, getBacktest: rpc.getBacktest },
  marketDataClient: { getMarketStatus: rpc.getMarketStatus },
  getTenantContext: () => tenantContext,
}));

import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { TransactionType } from '@llamatrade/core/proto/portfolio_pb';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';

const dec = (v: number | string) => ({ value: String(v) });
const ts = (seconds: number) => ({ seconds: BigInt(seconds) });

function perf(over: Record<string, unknown> = {}) {
  return {
    executionId: 'exec-1',
    strategyId: 'strat-1',
    strategyName: 'Momentum',
    color: '',
    allocatedCapital: dec(1000),
    positionsCount: 2,
    status: ExecutionStatus.RUNNING,
    returns: undefined,
    ...over,
  };
}

/** An absolute-equity curve; the store rebases it to a percentage series. */
function curve(values: number[], startSeconds = 1000) {
  return {
    equityCurve: values.map((v, i) => ({ equity: dec(v), timestamp: ts(startSeconds + i * 60) })),
    benchmark: undefined,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useDashboardStore.setState({
    totalEquity: 0,
    deployedValue: 0,
    freeCash: 0,
    totalReturn: 0,
    dayPnl: 0,
    liveStrategiesCount: 0,
    openPositionsCount: 0,
    atAllTimeHigh: false,
    strategies: [],
    portfolioCurve: [],
    benchmarkCurve: [],
    activity: [],
    loading: false,
    error: null,
  });
  rpc.listStrategyPerformance.mockResolvedValue({ strategies: [] });
  rpc.listStrategies.mockResolvedValue({ strategies: [] });
  rpc.listPortfolios.mockResolvedValue({ portfolios: [] });
  rpc.getStrategyEquityCurve.mockResolvedValue(curve([]));
  rpc.listBacktests.mockResolvedValue({ backtests: [] });
  rpc.listTransactions.mockResolvedValue({ transactions: [] });
  rpc.getMarketStatus.mockResolvedValue({});
});

describe('signed out', () => {
  it('resets to empty without calling the services', async () => {
    tenantContext = undefined;
    useDashboardStore.setState({ totalEquity: 999 });

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.totalEquity).toBe(0);
    expect(state.error).toBeNull();
    expect(rpc.listStrategyPerformance).not.toHaveBeenCalled();
  });
});

describe('deployed value and KPIs', () => {
  it('marks deployed capital to the latest curve point', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([1000, 1200]));

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.deployedValue).toBe(1200);
    // No account summary, so the return is derived against allocated capital.
    expect(state.totalReturn).toBe(200);
    expect(state.totalReturnPercent).toBeCloseTo(20);
  });

  it('falls back to allocated capital when a curve is missing', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockRejectedValue(new Error('no curve'));

    await useDashboardStore.getState().fetchDashboard();

    // Under-reporting the book would be worse than showing capital at cost.
    expect(useDashboardStore.getState().deployedValue).toBe(1000);
  });

  it('prefers the account summary over derived figures', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([1000, 1200]));
    rpc.listPortfolios.mockResolvedValue({
      portfolios: [
        {
          id: 'p1',
          totalValue: dec(5000),
          cashBalance: dec(3800),
          totalReturn: dec(42),
          totalReturnPercent: dec(1.5),
          dayReturn: dec(7),
          dayReturnPercent: dec(0.2),
        },
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.totalEquity).toBe(5000);
    expect(state.freeCash).toBe(3800);
    expect(state.totalReturn).toBe(42);
    expect(state.dayPnl).toBe(7);
    expect(state.freeCashPercent).toBeCloseTo(76);
  });

  it('counts only running strategies as live and sums open positions', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [
        perf({ executionId: 'e1', status: ExecutionStatus.RUNNING, positionsCount: 2 }),
        perf({ executionId: 'e2', status: ExecutionStatus.STOPPED, positionsCount: 3 }),
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.liveStrategiesCount).toBe(1);
    expect(state.openPositionsCount).toBe(5);
    expect(state.strategies.map((s) => s.isLive)).toEqual([true, false]);
  });

  it('converts percentage returns to fractions', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf({ returns: { return1d: dec(2.5), return1m: dec(10) } })],
    });

    await useDashboardStore.getState().fetchDashboard();

    const strategy = useDashboardStore.getState().strategies[0];
    expect(strategy.dayReturn).toBeCloseTo(0.025);
    expect(strategy.returns['1M']).toBeCloseTo(0.1);
  });
});

describe('curves', () => {
  it('rebases each strategy curve to a percentage series from its first point', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([100, 110, 90]));

    await useDashboardStore.getState().fetchDashboard();

    const values = useDashboardStore.getState().strategies[0].curve.map((p) => p.value);
    expect(values[0]).toBeCloseTo(0);
    expect(values[1]).toBeCloseTo(10);
    expect(values[2]).toBeCloseTo(-10);
  });

  it('right-anchors a shorter leg with its allocated capital', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [
        perf({ executionId: 'e1', allocatedCapital: dec(100) }),
        perf({ executionId: 'e2', allocatedCapital: dec(100) }),
      ],
    });
    rpc.getStrategyEquityCurve
      .mockResolvedValueOnce(curve([100, 100, 120])) // full history
      .mockResolvedValueOnce(curve([100, 100])); // joined late

    await useDashboardStore.getState().fetchDashboard();

    const values = useDashboardStore.getState().portfolioCurve.map((p) => p.value);
    // Before the short leg starts it contributes its baseline, so the blended
    // series starts flat at 0 rather than jumping when the leg appears.
    expect(values).toHaveLength(3);
    expect(values[0]).toBeCloseTo(0);
    expect(values[1]).toBeCloseTo(0);
    expect(values[2]).toBeCloseTo(10);
  });

  it('flags an all-time high only when the last point is the maximum', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([100, 110, 120]));

    await useDashboardStore.getState().fetchDashboard();
    expect(useDashboardStore.getState().atAllTimeHigh).toBe(true);

    rpc.getStrategyEquityCurve.mockResolvedValue(curve([100, 130, 120]));
    await useDashboardStore.getState().fetchDashboard();
    expect(useDashboardStore.getState().atAllTimeHigh).toBe(false);
  });

  it('takes the benchmark overlay from the first curve that carries one', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf({ executionId: 'e1' }), perf({ executionId: 'e2' })],
    });
    rpc.getStrategyEquityCurve
      .mockResolvedValueOnce({ ...curve([100, 110]), benchmark: undefined })
      .mockResolvedValueOnce({ ...curve([100, 105]), benchmark: curve([50, 55]) });

    await useDashboardStore.getState().fetchDashboard();

    const bench = useDashboardStore.getState().benchmarkCurve.map((p) => p.value);
    expect(bench[0]).toBeCloseTo(0);
    expect(bench[1]).toBeCloseTo(10);
  });
});

describe('activity feed', () => {
  const summary = {
    portfolios: [{ id: 'p1', totalValue: dec(100), cashBalance: dec(100) }],
  };

  it('keeps fills and dividends and drops types it cannot render', async () => {
    rpc.listPortfolios.mockResolvedValue(summary);
    rpc.listTransactions.mockResolvedValue({
      transactions: [
        {
          id: 'a',
          type: TransactionType.BUY,
          symbol: 'AAPL',
          quantity: dec(5),
          price: dec(10),
          amount: dec(50),
          timestamp: ts(300),
          description: '',
          referenceId: '',
        },
        {
          id: 'b',
          type: TransactionType.DEPOSIT,
          symbol: '',
          amount: dec(100),
          timestamp: ts(200),
          description: '',
          referenceId: '',
        },
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    const activity = useDashboardStore.getState().activity;
    expect(activity.map((a) => a.id)).toEqual(['a']);
    expect(activity[0].kind).toBe('buy');
    expect(activity[0].title).toContain('AAPL');
  });

  it('merges completed backtests newest first and caps the feed', async () => {
    rpc.listPortfolios.mockResolvedValue(summary);
    rpc.listTransactions.mockResolvedValue({
      transactions: [
        {
          id: 'trade',
          type: TransactionType.BUY,
          symbol: 'AAPL',
          quantity: dec(1),
          price: dec(1),
          amount: dec(1),
          timestamp: ts(100),
          description: '',
          referenceId: '',
        },
      ],
    });
    rpc.listBacktests.mockResolvedValue({
      backtests: [
        { id: 'bt1', strategyId: 'strat-1', status: 3, completedAt: ts(900), createdAt: ts(800) },
        { id: 'bt2', strategyId: 'strat-1', status: 1, completedAt: undefined, createdAt: ts(850) },
      ],
    });
    rpc.getBacktest.mockImplementation(({ backtestId }: { backtestId: string }) =>
      Promise.resolve({ backtest: { id: backtestId, strategyId: 'strat-1', completedAt: ts(900) } })
    );

    await useDashboardStore.getState().fetchDashboard();

    const activity = useDashboardStore.getState().activity;
    // Only the COMPLETED run is shown, and it is newer than the trade.
    expect(activity.map((a) => a.id)).toEqual(['bt-bt1', 'trade']);
    expect(activity.length).toBeLessThanOrEqual(6);
  });
});

describe('failures', () => {
  it('records an error when the driving read fails', async () => {
    rpc.listStrategyPerformance.mockRejectedValue(new Error('portfolio down'));

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.error).toBeTruthy();
    expect(state.loading).toBe(false);
  });

  it('still renders when the optional strategy list is unavailable', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.listStrategies.mockRejectedValue(new Error('strategy down'));

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.error).toBeNull();
    expect(state.strategies).toHaveLength(1);
    expect(state.strategies[0].descriptor).toBe('');
  });
});
