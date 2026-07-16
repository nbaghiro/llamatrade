import { beforeEach, describe, expect, it, vi } from 'vitest';

// eslint-disable-next-line import/order -- resolver misclassifies the gitignored generated/ path
import { BacktestStatus } from '../../generated/proto/backtest_pb';

const { listBacktests, getBacktest } = vi.hoisted(() => ({
  listBacktests: vi.fn(),
  getBacktest: vi.fn(),
}));

vi.mock('../../services/grpc-client', () => ({
  backtestClient: { listBacktests, getBacktest },
  strategyClient: {},
}));

vi.mock('../auth', () => ({
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

import { useBacktestStore } from '../backtest';

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
