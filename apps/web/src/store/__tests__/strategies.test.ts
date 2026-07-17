/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getStrategy, listStrategies, listStrategyPerformance } = vi.hoisted(() => ({
  getStrategy: vi.fn(),
  listStrategies: vi.fn(),
  listStrategyPerformance: vi.fn(),
}));

// The store now lives in @llamatrade/core and imports its clients + tenant
// context from @llamatrade/core/net, so the mock targets that module.
vi.mock('@llamatrade/core/net', () => ({
  strategyClient: { getStrategy, listStrategies },
  portfolioClient: { listStrategyPerformance },
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

import { useStrategiesStore } from '@llamatrade/core/stores/strategies';

type CachedStrategy = ReturnType<typeof useStrategiesStore.getState>['details'][string];

function fakeStrategy(id: string, dslCode = '(strategy :name "x")'): CachedStrategy {
  return { id, dslCode } as unknown as CachedStrategy;
}

describe('fetchStrategyDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStrategiesStore.setState({ details: {}, detailLoading: {} });
  });

  it('hydrates and caches the full strategy on success', async () => {
    const strategy = fakeStrategy('s1');
    getStrategy.mockResolvedValue({ strategy });

    await useStrategiesStore.getState().fetchStrategyDetail('s1');

    expect(getStrategy).toHaveBeenCalledTimes(1);
    expect(useStrategiesStore.getState().details.s1).toBe(strategy);
    expect(useStrategiesStore.getState().detailLoading.s1).toBeUndefined();
  });

  it('does not refetch an already-cached detail', async () => {
    getStrategy.mockResolvedValue({ strategy: fakeStrategy('s1') });

    await useStrategiesStore.getState().fetchStrategyDetail('s1');
    await useStrategiesStore.getState().fetchStrategyDetail('s1');

    expect(getStrategy).toHaveBeenCalledTimes(1);
  });

  it('dedups concurrent fetches for the same id', async () => {
    let resolve!: (value: { strategy: CachedStrategy }) => void;
    getStrategy.mockReturnValue(new Promise((r) => (resolve = r)));

    const first = useStrategiesStore.getState().fetchStrategyDetail('s1');
    const second = useStrategiesStore.getState().fetchStrategyDetail('s1');

    expect(useStrategiesStore.getState().detailLoading.s1).toBe(true);

    resolve({ strategy: fakeStrategy('s1') });
    await Promise.all([first, second]);

    expect(getStrategy).toHaveBeenCalledTimes(1);
    expect(useStrategiesStore.getState().details.s1).toBeDefined();
  });

  it('swallows errors and clears the loading flag', async () => {
    getStrategy.mockRejectedValue(new Error('boom'));

    await useStrategiesStore.getState().fetchStrategyDetail('s1');

    expect(useStrategiesStore.getState().details.s1).toBeUndefined();
    expect(useStrategiesStore.getState().detailLoading.s1).toBeUndefined();
  });
});

describe('fetchStrategies detail-cache reset', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStrategiesStore.setState({ details: {}, detailLoading: {} });
  });

  it('drops cached details so a refreshed list re-hydrates', async () => {
    listStrategies.mockResolvedValue({
      strategies: [],
      pagination: { totalItems: 0, totalPages: 1 },
    });
    useStrategiesStore.setState({ details: { s1: fakeStrategy('s1') } });

    await useStrategiesStore.getState().fetchStrategies();

    expect(useStrategiesStore.getState().details).toEqual({});
  });
});
