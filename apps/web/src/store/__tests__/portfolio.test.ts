/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const rpc = vi.hoisted(() => ({
  listStrategyPerformance: vi.fn(),
  listPortfolios: vi.fn(),
  getStrategyPerformance: vi.fn(),
  listSleeves: vi.fn(),
  getSleeve: vi.fn(),
  getOrCreateAccount: vi.fn(),
  listAlpacaCredentials: vi.fn(),
  listStrategies: vi.fn(),
  getStrategy: vi.fn(),
}));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  portfolioClient: {
    listStrategyPerformance: rpc.listStrategyPerformance,
    listPortfolios: rpc.listPortfolios,
    getStrategyPerformance: rpc.getStrategyPerformance,
  },
  ledgerClient: {
    listSleeves: rpc.listSleeves,
    getSleeve: rpc.getSleeve,
    getOrCreateAccount: rpc.getOrCreateAccount,
  },
  authClient: { listAlpacaCredentials: rpc.listAlpacaCredentials },
  strategyClient: { listStrategies: rpc.listStrategies, getStrategy: rpc.getStrategy },
  getTenantContext: () => tenantContext,
}));

import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus, SleeveType } from '@llamatrade/core/proto/ledger_pb';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import {
  isOpenSleeve,
  ledgerQuantities,
  usePortfolioStore,
} from '@llamatrade/core/stores/portfolio';

const dec = (v: number | string) => ({ value: String(v) });
const ts = (seconds: number) => ({ seconds: BigInt(seconds) });
const FUNDING = useFundingStore.getState();

function perf(over: Record<string, unknown> = {}) {
  return {
    executionId: 'exec-1',
    strategyId: 'strat-1',
    strategyName: 'All-Weather',
    status: ExecutionStatus.RUNNING,
    allocatedCapital: dec(35000),
    currentValue: dec(35982.55),
    positionsCount: 2,
    returns: { return1d: dec(-0.2) },
    startedAt: ts(1_754_000_000),
    ...over,
  };
}

function sleeve(over: Record<string, unknown> = {}) {
  return {
    id: 'sl-1',
    type: SleeveType.STRATEGY,
    status: SleeveStatus.ACTIVE,
    name: 'All-Weather',
    strategyExecutionId: 'exec-1',
    allocatedCapital: dec(35000),
    cash: { balance: dec(120.5), reserved: dec(0) },
    ...over,
  };
}

const unallocatedSleeve = {
  id: 'sl-u',
  type: SleeveType.UNALLOCATED,
  status: SleeveStatus.ACTIVE,
  cash: { balance: dec(17100), reserved: dec(22.88) },
};

function position(symbol: string, marketValue: number) {
  return {
    symbol,
    quantity: dec(10),
    currentPrice: dec(marketValue / 10),
    averageEntryPrice: dec(1),
    marketValue: dec(marketValue),
    unrealizedPnl: dec(5),
  };
}

function primeAccount() {
  rpc.listAlpacaCredentials.mockResolvedValue({
    credentials: [{ id: 'cred-1', isPaper: true, isActive: true }],
  });
  rpc.getOrCreateAccount.mockResolvedValue({ account: { id: 'acct-1' }, baseSleeves: [] });
}

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useFundingStore.setState({ ...FUNDING, accountId: null, resolved: false, resolving: false });
  usePortfolioStore.setState({
    sleeves: [],
    unallocated: null,
    summaryTotal: 0,
    loading: false,
    loaded: false,
    error: null,
    sleeve: null,
    sleeveLoading: false,
    sleeveError: null,
  });
  primeAccount();
  rpc.listStrategyPerformance.mockResolvedValue({ strategies: [perf()] });
  rpc.listPortfolios.mockResolvedValue({ portfolios: [{ totalValue: dec(103410.27) }] });
  rpc.listSleeves.mockResolvedValue({ sleeves: [sleeve(), unallocatedSleeve] });
  rpc.getStrategyPerformance.mockResolvedValue({
    positions: [position('VTI', 12000), position('VGLT', 13000)],
  });
  rpc.listStrategies.mockResolvedValue({
    strategies: [{ id: 'strat-1', rebalance: 'quarterly', dslCode: '' }],
  });
});

describe('fetchPortfolio', () => {
  it('reads target weights from a strategy whose weights are fixed', async () => {
    rpc.listStrategies.mockResolvedValue({
      strategies: [
        {
          id: 'strat-1',
          rebalance: 'quarterly',
          dslCode:
            '(strategy "AW" (weight :method specified (asset VGLT :weight 40) (group "Eq" :weight 60 (weight :method equal (asset VTI) (asset VEA)))))',
        },
      ],
    });
    await usePortfolioStore.getState().fetchPortfolio();
    const [s] = usePortfolioStore.getState().sleeves;
    expect(s.targets.VGLT).toBeCloseTo(0.4);
    expect(s.targets.VTI).toBeCloseTo(0.3);
    expect(s.targets.VEA).toBeCloseTo(0.3);
  });

  it('leaves targets empty when a rule decides the holdings', async () => {
    rpc.listStrategies.mockResolvedValue({
      strategies: [
        {
          id: 'strat-1',
          rebalance: 'monthly',
          dslCode:
            '(strategy "M" (if (> (price SPY) (sma SPY 200)) (asset SPY) (else (asset IEF))))',
        },
      ],
    });
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().sleeves[0].targets).toEqual({});
  });

  it('resets to a clean empty state when signed out, never to mock data', async () => {
    tenantContext = undefined;
    await usePortfolioStore.getState().fetchPortfolio();
    const s = usePortfolioStore.getState();
    expect(s.sleeves).toEqual([]);
    expect(s.unallocated).toBeNull();
    expect(s.loaded).toBe(true);
    expect(rpc.listStrategyPerformance).not.toHaveBeenCalled();
  });

  it('joins each execution to its ledger sleeve, holdings and rebalance schedule', async () => {
    await usePortfolioStore.getState().fetchPortfolio();
    const [s] = usePortfolioStore.getState().sleeves;
    expect(s).toMatchObject({
      executionId: 'exec-1',
      sleeveId: 'sl-1',
      name: 'All-Weather',
      frozen: false,
      allocatedCapital: 35000,
      value: 35982.55,
      dayReturnPct: -0.2,
      rebalance: 'quarterly',
      cash: 120.5,
    });
    expect(s.holdings.map((h) => [h.symbol, h.marketValue])).toEqual([
      ['VTI', 12000],
      ['VGLT', 13000],
    ]);
    expect(s.startedAt?.getTime()).toBe(1_754_000_000_000);
    expect(s.targets).toEqual({});
    expect(rpc.listSleeves).toHaveBeenCalledWith(expect.objectContaining({ accountId: 'acct-1' }));
  });

  it('reads unallocated as the ledger sleeve’s free cash, net of reservations', async () => {
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().unallocated).toBeCloseTo(17077.12);
    expect(usePortfolioStore.getState().summaryTotal).toBe(103410.27);
  });

  it('marks a sleeve frozen from the ledger, whatever the execution reports', async () => {
    rpc.listSleeves.mockResolvedValue({
      sleeves: [sleeve({ status: SleeveStatus.FROZEN }), unallocatedSleeve],
    });
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().sleeves[0].frozen).toBe(true);
  });

  it('leaves closed sleeves off the overview', async () => {
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf(), perf({ executionId: 'exec-2', strategyName: 'Classic 60/40' })],
    });
    rpc.listSleeves.mockResolvedValue({
      sleeves: [
        sleeve(),
        sleeve({ id: 'sl-2', strategyExecutionId: 'exec-2', status: SleeveStatus.CLOSED }),
        unallocatedSleeve,
      ],
    });
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().sleeves.map((s) => s.executionId)).toEqual(['exec-1']);
  });

  it('keeps the page working without the ledger, with no unallocated figure or sleeve ids', async () => {
    rpc.listSleeves.mockRejectedValue(new Error('ledger down'));
    await usePortfolioStore.getState().fetchPortfolio();
    const s = usePortfolioStore.getState();
    expect(s.error).toBeNull();
    expect(s.unallocated).toBeNull();
    expect(s.sleeves[0].sleeveId).toBeNull();
    expect(s.sleeves[0].cash).toBeNull();
  });

  it('drops stopped executions when the ledger is unavailable', async () => {
    rpc.listSleeves.mockRejectedValue(new Error('ledger down'));
    rpc.listStrategyPerformance.mockResolvedValue({
      strategies: [perf(), perf({ executionId: 'exec-2', status: ExecutionStatus.STOPPED })],
    });
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().sleeves).toHaveLength(1);
  });

  it('has no unallocated figure when no paper account is connected', async () => {
    rpc.listAlpacaCredentials.mockResolvedValue({ credentials: [] });
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().unallocated).toBeNull();
    expect(rpc.listSleeves).not.toHaveBeenCalled();
  });

  it('shows a sleeve with no holdings when its detail read fails', async () => {
    rpc.getStrategyPerformance.mockRejectedValue(new Error('boom'));
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().sleeves[0].holdings).toEqual([]);
  });

  it('leaves the schedule empty when strategies can’t be listed', async () => {
    rpc.listStrategies.mockRejectedValue(new Error('down'));
    await usePortfolioStore.getState().fetchPortfolio();
    expect(usePortfolioStore.getState().sleeves[0].rebalance).toBe('');
  });

  it('records an error and keeps the last figures when the driving read fails', async () => {
    await usePortfolioStore.getState().fetchPortfolio();
    rpc.listStrategyPerformance.mockRejectedValue(new Error('portfolio down'));
    await usePortfolioStore.getState().fetchPortfolio();
    const s = usePortfolioStore.getState();
    expect(s.error).toBe('portfolio down');
    expect(s.loading).toBe(false);
    expect(s.sleeves).toHaveLength(1);
  });

  it('clearError resets the message', () => {
    usePortfolioStore.setState({ error: 'x' });
    usePortfolioStore.getState().clearError();
    expect(usePortfolioStore.getState().error).toBeNull();
  });
});

describe('fetchSleeve', () => {
  beforeEach(() => {
    rpc.getSleeve.mockResolvedValue({
      sleeve: sleeve({ status: SleeveStatus.FROZEN }),
      lots: [
        { symbol: 'TLT', qty: dec(100), avgPrice: dec(89.82), isOpen: true, openedAt: ts(10) },
        { symbol: 'TLT', qty: dec(67), avgPrice: dec(90), isOpen: true, openedAt: ts(20) },
        { symbol: 'GLD', qty: dec(41), avgPrice: dec(243.9), isOpen: true, openedAt: ts(30) },
        { symbol: 'VTI', qty: dec(30), avgPrice: dec(400), isOpen: false, openedAt: ts(5) },
      ],
    });
    rpc.getStrategyPerformance.mockResolvedValue({
      summary: perf(),
      positions: [position('TLT', 15000)],
    });
    rpc.getStrategy.mockResolvedValue({
      strategy: {
        rebalance: 'monthly',
        dslCode:
          '(strategy "S" (weight :method specified (asset VTI :weight 60) (asset BND :weight 40)))',
      },
    });
  });

  it('combines the ledger sleeve, its open lots and the strategy’s positions', async () => {
    await usePortfolioStore.getState().fetchSleeve('sl-1');
    const s = usePortfolioStore.getState().sleeve;
    expect(s).toMatchObject({
      sleeveId: 'sl-1',
      name: 'All-Weather',
      frozen: true,
      rebalance: 'monthly',
      ledgerQty: { TLT: 167, GLD: 41 },
    });
    expect(s?.lots).toHaveLength(3);
    expect(s?.holdings.map((h) => h.symbol)).toEqual(['TLT']);
    expect(rpc.getStrategy).toHaveBeenCalledWith(
      expect.objectContaining({ strategyId: 'strat-1' })
    );
  });

  it('falls back to the ledger sleeve alone when it has no execution', async () => {
    rpc.getSleeve.mockResolvedValue({
      sleeve: sleeve({ strategyExecutionId: '', name: 'Manual' }),
      lots: [],
    });
    await usePortfolioStore.getState().fetchSleeve('sl-1');
    const s = usePortfolioStore.getState().sleeve;
    expect(s?.name).toBe('Manual');
    expect(s?.value).toBe(120.5);
    expect(rpc.getStrategyPerformance).not.toHaveBeenCalled();
  });

  it('reports a missing or failed sleeve without keeping another sleeve’s data', async () => {
    await usePortfolioStore.getState().fetchSleeve('sl-1');
    rpc.getSleeve.mockResolvedValue({ sleeve: undefined, lots: [] });
    await usePortfolioStore.getState().fetchSleeve('sl-9');
    const s = usePortfolioStore.getState();
    expect(s.sleeve).toBeNull();
    expect(s.sleeveError).toMatch(/could not be found/);
    expect(s.sleeveLoading).toBe(false);
  });
});

describe('helpers', () => {
  it('sums open ledger quantity per symbol', () => {
    expect(
      ledgerQuantities([
        { symbol: 'A', qty: 1, avgPrice: 1, openedAt: null },
        { symbol: 'A', qty: 2.5, avgPrice: 1, openedAt: null },
        { symbol: 'B', qty: 4, avgPrice: 1, openedAt: null },
      ])
    ).toEqual({ A: 3.5, B: 4 });
    expect(ledgerQuantities([])).toEqual({});
  });

  it('decides which sleeves still hold capital', () => {
    const open = { status: SleeveStatus.ACTIVE } as Parameters<typeof isOpenSleeve>[1];
    const closed = { status: SleeveStatus.CLOSED } as Parameters<typeof isOpenSleeve>[1];
    expect(isOpenSleeve(ExecutionStatus.STOPPED, open)).toBe(true);
    expect(isOpenSleeve(ExecutionStatus.RUNNING, closed)).toBe(false);
    expect(isOpenSleeve(ExecutionStatus.PAUSED, undefined)).toBe(true);
    expect(isOpenSleeve(ExecutionStatus.STOPPED, undefined)).toBe(false);
  });
});
