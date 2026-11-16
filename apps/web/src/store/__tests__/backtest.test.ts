/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listBacktests, getBacktest, compareBacktests, streamBacktestProgress, getStrategy } =
  vi.hoisted(() => ({
    listBacktests: vi.fn(),
    getBacktest: vi.fn(),
    compareBacktests: vi.fn(),
    streamBacktestProgress: vi.fn(),
    getStrategy: vi.fn(),
  }));

vi.mock('@llamatrade/core/net', () => ({
  backtestClient: { listBacktests, getBacktest, compareBacktests, streamBacktestProgress },
  strategyClient: { getStrategy },
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';

type Run = NonNullable<ReturnType<typeof useBacktestStore.getState>['currentBacktest']>;

function run(id: string, status: number, completedAtSec: number): Run {
  return {
    id,
    status,
    completedAt: { seconds: BigInt(completedAtSec), nanos: 0 },
  } as unknown as Run;
}

describe('fetchLatestCompletedBacktest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBacktestStore.setState({ currentBacktest: null, backtests: [] });
  });

  it('returns null for an empty strategyId without hitting the API', async () => {
    const result = await useBacktestStore.getState().fetchLatestCompletedBacktest('');
    expect(result).toBeNull();
    expect(listBacktests).not.toHaveBeenCalled();
  });

  it('returns null (and skips hydration) when there are no completed runs', async () => {
    listBacktests.mockResolvedValue({ backtests: [run('a', BacktestStatus.FAILED, 100)] });

    const result = await useBacktestStore.getState().fetchLatestCompletedBacktest('s1');

    expect(result).toBeNull();
    expect(getBacktest).not.toHaveBeenCalled();
  });

  it('picks the newest completed run and returns its hydrated detail', async () => {
    listBacktests.mockResolvedValue({
      backtests: [
        run('old', BacktestStatus.COMPLETED, 100),
        run('new', BacktestStatus.COMPLETED, 200),
        run('later-but-failed', BacktestStatus.FAILED, 300),
      ],
    });
    const hydrated = run('new', BacktestStatus.COMPLETED, 200);
    getBacktest.mockResolvedValue({ backtest: hydrated });

    const result = await useBacktestStore.getState().fetchLatestCompletedBacktest('s1');

    expect(getBacktest).toHaveBeenCalledWith(expect.objectContaining({ backtestId: 'new' }));
    expect(result).toBe(hydrated);
  });

  it('does not clobber shared currentBacktest / backtests state', async () => {
    listBacktests.mockResolvedValue({ backtests: [run('new', BacktestStatus.COMPLETED, 200)] });
    getBacktest.mockResolvedValue({ backtest: run('new', BacktestStatus.COMPLETED, 200) });

    await useBacktestStore.getState().fetchLatestCompletedBacktest('s1');

    expect(useBacktestStore.getState().currentBacktest).toBeNull();
    expect(useBacktestStore.getState().backtests).toEqual([]);
  });

  it('returns null when the API call fails', async () => {
    listBacktests.mockRejectedValue(new Error('boom'));

    const result = await useBacktestStore.getState().fetchLatestCompletedBacktest('s1');

    expect(result).toBeNull();
  });
});

describe('loadHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBacktestStore.getState().reset();
  });

  it('sorts newest first and fetches metrics for completed runs only', async () => {
    listBacktests.mockResolvedValue({
      backtests: [
        run('old', BacktestStatus.COMPLETED, 100),
        run('failed', BacktestStatus.FAILED, 300),
        run('new', BacktestStatus.COMPLETED, 200),
      ],
      pagination: { totalItems: 38 },
    });
    compareBacktests.mockResolvedValue({ metricsById: { new: { totalTrades: 4 } } });

    await useBacktestStore.getState().loadHistory();

    const { history } = useBacktestStore.getState();
    expect(history.runs.map((r) => r.id)).toEqual(['failed', 'new', 'old']);
    expect(history.total).toBe(38);
    expect(compareBacktests.mock.calls[0][0].backtestIds).toEqual(['new', 'old']);
    expect(history.metrics.new.totalTrades).toBe(4);
    expect(history.loaded).toBe(true);
  });

  it('keeps the list when the metrics call fails and skips it with nothing completed', async () => {
    listBacktests.mockResolvedValue({ backtests: [run('a', BacktestStatus.COMPLETED, 1)] });
    compareBacktests.mockRejectedValue(new Error('down'));
    await useBacktestStore.getState().loadHistory();
    expect(useBacktestStore.getState().history.runs).toHaveLength(1);
    expect(useBacktestStore.getState().history.error).toBeNull();

    compareBacktests.mockClear();
    listBacktests.mockResolvedValue({ backtests: [run('b', BacktestStatus.CANCELLED, 1)] });
    await useBacktestStore.getState().loadHistory();
    expect(compareBacktests).not.toHaveBeenCalled();
  });

  it('reports a failed list', async () => {
    listBacktests.mockRejectedValue(new Error('Backtest service is down'));
    await useBacktestStore.getState().loadHistory();
    expect(useBacktestStore.getState().history).toMatchObject({
      loading: false,
      loaded: true,
      error: 'Backtest service is down',
    });
  });
});

describe('loadComparison', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBacktestStore.getState().reset();
  });

  it('keeps the requested order and drops runs that fail to load', async () => {
    compareBacktests.mockResolvedValue({ metricsById: { a: {}, c: {} } });
    getBacktest.mockImplementation(({ backtestId }: { backtestId: string }) =>
      backtestId === 'b'
        ? Promise.reject(new Error('gone'))
        : Promise.resolve({ backtest: { id: backtestId } })
    );

    await useBacktestStore.getState().loadComparison(['c', 'b', 'a']);

    const { comparison } = useBacktestStore.getState();
    expect(comparison.runs.map((r) => r.id)).toEqual(['c', 'a']);
    expect(Object.keys(comparison.metrics)).toEqual(['a', 'c']);
    expect(comparison.loading).toBe(false);
  });

  it('reports a failed compare', async () => {
    compareBacktests.mockRejectedValue(new Error('nope'));
    getBacktest.mockResolvedValue({});
    await useBacktestStore.getState().loadComparison(['a']);
    expect(useBacktestStore.getState().comparison.error).toBe('nope');
  });
});

describe('streamProgress', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBacktestStore.getState().reset();
  });

  it('records each update and the latest partial metrics, then loads the result', async () => {
    async function* updates() {
      yield {
        status: BacktestStatus.RUNNING,
        progressPercent: 50,
        currentDate: '2025-06-30',
        message: '',
        partialMetrics: { totalReturn: { value: '0.04' } },
      };
      yield {
        status: BacktestStatus.RUNNING,
        progressPercent: 70,
        currentDate: '2025-09-30',
        message: '',
      };
      yield {
        status: BacktestStatus.COMPLETED,
        progressPercent: 100,
        currentDate: '',
        message: '',
      };
    }
    streamBacktestProgress.mockReturnValue(updates());
    getBacktest.mockResolvedValue({ backtest: { id: 'r1', status: BacktestStatus.COMPLETED } });
    useBacktestStore.setState({ currentBacktest: run('r1', BacktestStatus.RUNNING, 0) });

    await useBacktestStore.getState().streamProgress('r1');

    const state = useBacktestStore.getState();
    expect(state.progressEvents.map((e) => e.currentDate)).toEqual([
      '2025-06-30',
      '2025-09-30',
      '',
    ]);
    expect(state.partialMetrics?.totalReturn?.value).toBe('0.04');
    expect(state.currentBacktest?.status).toBe(BacktestStatus.COMPLETED);
    expect(state.streaming).toBe(false);
    expect(state.runSubmittedAt).not.toBeNull();
  });

  it('clearRun forgets the watched run', () => {
    useBacktestStore.setState({
      currentBacktest: run('r1', BacktestStatus.RUNNING, 0),
      progressEvents: [{ status: 2, percent: 1, currentDate: '', message: '', atMs: 1 }],
      runSubmittedAt: 1,
    });
    useBacktestStore.getState().clearRun();
    const state = useBacktestStore.getState();
    expect(state.currentBacktest).toBeNull();
    expect(state.progressEvents).toEqual([]);
    expect(state.runSubmittedAt).toBeNull();
  });
});

describe('fetchVersionDsl', () => {
  it('asks for the exact version and returns its source', async () => {
    getStrategy.mockResolvedValue({ strategy: { dslCode: '(strategy "X")' } });
    expect(await useBacktestStore.getState().fetchVersionDsl('s1', 3)).toBe('(strategy "X")');
    expect(getStrategy.mock.calls[0][0]).toMatchObject({ strategyId: 's1', version: 3 });
    getStrategy.mockRejectedValue(new Error('x'));
    expect(await useBacktestStore.getState().fetchVersionDsl('s1', 3)).toBeNull();
  });
});
