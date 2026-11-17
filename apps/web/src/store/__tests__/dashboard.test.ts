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
  listAlpacaCredentials: vi.fn(),
  listSessions: vi.fn(),
  listOrders: vi.fn(),
  getOrCreateAccount: vi.fn(),
  listSleeves: vi.fn(),
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
  authClient: { listAlpacaCredentials: rpc.listAlpacaCredentials },
  tradingClient: { listSessions: rpc.listSessions, listOrders: rpc.listOrders },
  ledgerClient: { getOrCreateAccount: rpc.getOrCreateAccount, listSleeves: rpc.listSleeves },
  getTenantContext: () => tenantContext,
}));

import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { TransactionType } from '@llamatrade/core/proto/portfolio_pb';
import { OrderSide, OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { lastSnapshotChange, useDashboardStore } from '@llamatrade/core/stores/dashboard';

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
    equityAsOf: null,
    lastChange: null,
    strategyCount: null,
    completedBacktestCount: null,
    brokerConnected: null,
    sessionCount: null,
    frozenSleeves: null,
    rejectedOrders: null,
    loading: false,
    loaded: false,
    error: null,
  });
  rpc.listStrategyPerformance.mockResolvedValue({ strategies: [] });
  rpc.listStrategies.mockResolvedValue({ strategies: [] });
  rpc.listPortfolios.mockResolvedValue({ portfolios: [] });
  rpc.getStrategyEquityCurve.mockResolvedValue(curve([]));
  rpc.listBacktests.mockResolvedValue({ backtests: [] });
  rpc.listTransactions.mockResolvedValue({ transactions: [] });
  rpc.getMarketStatus.mockResolvedValue({});
  rpc.listAlpacaCredentials.mockResolvedValue({ credentials: [] });
  rpc.listSessions.mockResolvedValue({ sessions: [], pagination: { totalItems: 0 } });
  rpc.listOrders.mockResolvedValue({ orders: [] });
  rpc.getOrCreateAccount.mockResolvedValue({ account: { id: 'acct-1' }, baseSleeves: [] });
  rpc.listSleeves.mockResolvedValue({ sleeves: [] });
});

describe('signed out', () => {
  it('resets to empty without calling the services', async () => {
    tenantContext = undefined;
    useDashboardStore.setState({ totalEquity: 999 });

    await useDashboardStore.getState().fetchDashboard();

    const state = useDashboardStore.getState();
    expect(state.totalEquity).toBe(0);
    expect(state.error).toBeNull();
    expect(state.loaded).toBe(true);
    expect(state.sessionCount).toBeNull();
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

  it('keeps each strategy’s absolute equity, mode, value now and start', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf({ mode: 2, currentValue: dec(1234.5), startedAt: ts(500) })],
    });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([100, 110]));

    await useDashboardStore.getState().fetchDashboard();

    const s = useDashboardStore.getState().strategies[0];
    expect(s.equity.map((p) => p.value)).toEqual([100, 110]);
    expect(s.equity[1].timestamp).toBe(new Date(1060 * 1000).toISOString());
    expect(s.mode).toBe(2);
    expect(s.currentValue).toBe(1234.5);
    expect(s.startedAt?.getTime()).toBe(500_000);
  });

  it('leaves the value now unknown when the summary has none', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    await useDashboardStore.getState().fetchDashboard();
    expect(useDashboardStore.getState().strategies[0].currentValue).toBeNull();
    expect(useDashboardStore.getState().strategies[0].startedAt).toBeNull();
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

describe('activity wording', () => {
  it('writes fills as "qty symbol at price" with the strategy name first', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf({ strategyId: 'strat-1', strategyName: 'Tech Momentum' })],
    });
    rpc.listPortfolios.mockResolvedValue({ portfolios: [{ id: 'p1', totalValue: dec(1) }] });
    rpc.listTransactions.mockResolvedValue({
      transactions: [
        {
          id: 't',
          type: TransactionType.SELL,
          symbol: 'XLK',
          quantity: dec(38),
          price: dec(301.12),
          amount: dec(0),
          timestamp: ts(100),
          description: 'rebalance',
          referenceId: 'strat-1',
        },
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    const [item] = useDashboardStore.getState().activity;
    expect(item.title).toBe('38 XLK at $301.12');
    expect(item.subtitle).toBe('Tech Momentum · rebalance');
  });

  it('names a finished backtest and puts its figures underneath', async () => {
    rpc.listBacktests.mockResolvedValue({
      backtests: [{ id: 'bt', strategyId: 'strat-1', status: 3, completedAt: ts(9) }],
    });
    rpc.listStrategies.mockResolvedValue({
      strategies: [{ id: 'strat-1', name: 'Radar', symbols: [] }],
    });
    rpc.getBacktest.mockResolvedValue({
      backtest: {
        id: 'bt',
        strategyId: 'strat-1',
        completedAt: ts(9),
        results: { metrics: { totalReturn: dec(0.214), sharpeRatio: dec(0.79) } },
      },
    });

    await useDashboardStore.getState().fetchDashboard();

    const [item] = useDashboardStore.getState().activity;
    expect(item.title).toBe('Radar backtest completed');
    expect(item.subtitle).toBe('+21.4% · Sharpe 0.79');
  });

  it('says "Backtest completed" once when the strategy name is unknown', async () => {
    rpc.listBacktests.mockResolvedValue({
      backtests: [{ id: 'bt', strategyId: 'gone', status: 3, completedAt: ts(9) }],
    });
    rpc.getBacktest.mockResolvedValue({
      backtest: { id: 'bt', strategyId: 'gone', completedAt: ts(9) },
    });

    await useDashboardStore.getState().fetchDashboard();

    const [item] = useDashboardStore.getState().activity;
    expect(item.title).toBe('Backtest completed');
  });
});

describe('strategy descriptor', () => {
  it('prefers the rebalance cadence, then the symbol count', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [
        perf({ executionId: 'e1', strategyId: 's1' }),
        perf({ executionId: 'e2', strategyId: 's2' }),
      ],
    });
    rpc.listStrategies.mockResolvedValue({
      strategies: [
        {
          id: 's1',
          name: 'A',
          rebalance: 'QUARTERLY',
          templateId: 'classic-60-40',
          symbols: ['SPY'],
        },
        { id: 's2', name: 'B', rebalance: '', templateId: '', symbols: ['SPY', 'AGG'] },
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    expect(useDashboardStore.getState().strategies.map((s) => s.descriptor)).toEqual([
      'Quarterly',
      '2 symbols',
    ]);
  });
});

describe('setup facts', () => {
  it('reads strategy, backtest, broker and session counts', async () => {
    rpc.listStrategies.mockResolvedValue({
      strategies: [{ id: 's1', name: 'A', symbols: [] }],
      pagination: { totalItems: 4 },
    });
    rpc.listBacktests.mockResolvedValue({
      backtests: [
        { id: 'b1', strategyId: 's1', status: 3, completedAt: ts(5) },
        { id: 'b2', strategyId: 's1', status: 4, createdAt: ts(6) },
      ],
    });
    rpc.getBacktest.mockResolvedValue({ backtest: { id: 'b1', strategyId: 's1' } });
    rpc.listAlpacaCredentials.mockResolvedValue({
      credentials: [{ id: 'c1', isPaper: true, isActive: true }],
    });
    rpc.listSessions.mockResolvedValue({ sessions: [{ id: 'x' }], pagination: { totalItems: 3 } });

    await useDashboardStore.getState().fetchDashboard();

    const s = useDashboardStore.getState();
    expect(s.loaded).toBe(true);
    expect(s.strategyCount).toBe(4);
    expect(s.completedBacktestCount).toBe(1);
    expect(s.brokerConnected).toBe(true);
    expect(s.sessionCount).toBe(3);
  });

  it('reports a new account as empty rather than unknown', async () => {
    await useDashboardStore.getState().fetchDashboard();

    const s = useDashboardStore.getState();
    expect(s.strategyCount).toBe(0);
    expect(s.completedBacktestCount).toBe(0);
    expect(s.brokerConnected).toBe(false);
    expect(s.sessionCount).toBe(0);
    expect(s.frozenSleeves).toEqual([]);
    expect(s.rejectedOrders).toEqual([]);
    // No credential means no ledger account to read.
    expect(rpc.getOrCreateAccount).not.toHaveBeenCalled();
  });

  it('keeps a failed read as null so the page does not guess', async () => {
    rpc.listStrategies.mockRejectedValue(new Error('down'));
    rpc.listBacktests.mockRejectedValue(new Error('down'));
    rpc.listAlpacaCredentials.mockRejectedValue(new Error('down'));
    rpc.listSessions.mockRejectedValue(new Error('down'));
    rpc.listOrders.mockRejectedValue(new Error('down'));

    await useDashboardStore.getState().fetchDashboard();

    const s = useDashboardStore.getState();
    expect(s.error).toBeNull();
    expect(s.strategyCount).toBeNull();
    expect(s.completedBacktestCount).toBeNull();
    expect(s.brokerConnected).toBeNull();
    expect(s.sessionCount).toBeNull();
    expect(s.frozenSleeves).toBeNull();
    expect(s.rejectedOrders).toBeNull();
  });

  it('treats an inactive or live-only credential set as not connected for paper', async () => {
    rpc.listAlpacaCredentials.mockResolvedValue({
      credentials: [{ id: 'c1', isPaper: true, isActive: false }],
    });

    await useDashboardStore.getState().fetchDashboard();

    expect(useDashboardStore.getState().brokerConnected).toBe(false);
  });
});

describe('attention sources', () => {
  it('lists frozen sleeves from the paper ledger account, named after their strategy', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf({ executionId: 'e1', strategyName: 'Recession Radar' })],
    });
    rpc.listAlpacaCredentials.mockResolvedValue({
      credentials: [
        { id: 'live', isPaper: false, isActive: true },
        { id: 'paper', isPaper: true, isActive: true },
      ],
    });
    rpc.listSleeves.mockResolvedValue({
      sleeves: [
        { id: 'sl1', name: 'sleeve-e1', status: SleeveStatus.FROZEN, strategyExecutionId: 'e1' },
        { id: 'sl2', name: 'Unallocated', status: SleeveStatus.ACTIVE, strategyExecutionId: '' },
        { id: 'sl3', name: 'Orphan', status: SleeveStatus.FROZEN, strategyExecutionId: 'gone' },
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    expect(rpc.getOrCreateAccount).toHaveBeenCalledWith(
      expect.objectContaining({ credentialsId: 'paper' })
    );
    expect(rpc.listSleeves).toHaveBeenCalledWith(expect.objectContaining({ accountId: 'acct-1' }));
    expect(useDashboardStore.getState().frozenSleeves).toEqual([
      { id: 'sl1', name: 'Recession Radar', executionId: 'e1' },
      { id: 'sl3', name: 'Orphan', executionId: 'gone' },
    ]);
  });

  it('records a failed ledger read as null', async () => {
    rpc.listAlpacaCredentials.mockResolvedValue({
      credentials: [{ id: 'paper', isPaper: true, isActive: true }],
    });
    rpc.listSleeves.mockRejectedValue(new Error('ledger down'));

    await useDashboardStore.getState().fetchDashboard();

    expect(useDashboardStore.getState().frozenSleeves).toBeNull();
  });

  it('keeps only rejected orders, with their reason and time', async () => {
    rpc.listOrders.mockResolvedValue({
      orders: [
        {
          id: 'o1',
          symbol: 'TLT',
          side: OrderSide.BUY,
          quantity: dec(47),
          status: OrderStatus.REJECTED,
          statusMessage: 'insufficient buying power',
          submittedAt: ts(500),
          strategyId: 's1',
          sessionId: 'se1',
        },
        { id: 'o2', symbol: 'SPY', side: OrderSide.SELL, status: OrderStatus.FILLED },
      ],
    });

    await useDashboardStore.getState().fetchDashboard();

    expect(rpc.listOrders).toHaveBeenCalledWith(
      expect.objectContaining({ statuses: [OrderStatus.REJECTED] })
    );
    const rejected = useDashboardStore.getState().rejectedOrders;
    expect(rejected).toHaveLength(1);
    expect(rejected?.[0]).toMatchObject({
      id: 'o1',
      symbol: 'TLT',
      quantity: 47,
      message: 'insufficient buying power',
    });
    expect(rejected?.[0].at?.getTime()).toBe(500_000);
  });
});

describe('last snapshot change', () => {
  it('reports the move between the last two snapshots and when it started', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
    rpc.getStrategyEquityCurve.mockResolvedValue(curve([1000, 1100, 1210], 1000));
    rpc.listPortfolios.mockResolvedValue({
      portfolios: [{ id: 'p1', totalValue: dec(2210), cashBalance: dec(1000) }],
    });

    await useDashboardStore.getState().fetchDashboard();

    const s = useDashboardStore.getState();
    expect(s.lastChange?.amount).toBeCloseTo(110);
    // 110 on an account of 2,100 before the move.
    expect(s.lastChange?.fraction).toBeCloseTo(110 / 2100);
    expect(s.lastChange?.since?.getTime()).toBe((1000 + 60) * 1000);
    expect(s.equityAsOf?.getTime()).toBe((1000 + 120) * 1000);
  });

  it('is null with fewer than two snapshots', () => {
    expect(
      lastSnapshotChange({ absolute: [5], timestamps: ['2026-01-01T00:00:00Z'] }, 5)
    ).toBeNull();
  });

  it('avoids dividing by an empty account', () => {
    const change = lastSnapshotChange(
      { absolute: [0, 10], timestamps: ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'] },
      10
    );
    expect(change?.amount).toBe(10);
    expect(change?.fraction).toBe(0);
  });
});

describe('loaded flag', () => {
  it('is set after a failed load too, so the page can leave its skeleton', async () => {
    rpc.listStrategyPerformance.mockRejectedValue(new Error('down'));
    await useDashboardStore.getState().fetchDashboard();
    expect(useDashboardStore.getState().loaded).toBe(true);
  });
});
