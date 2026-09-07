/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listTransactions } = vi.hoisted(() => ({ listTransactions: vi.fn() }));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  portfolioClient: { listTransactions },
  getTenantContext: () => tenantContext,
}));

import { TransactionType } from '@llamatrade/core/proto/portfolio_pb';
import { useActivityStore } from '@llamatrade/core/stores/activity';

function txn(over: Record<string, unknown> = {}) {
  return {
    id: 'tx-1',
    type: TransactionType.DEPOSIT,
    amount: { value: '100' },
    timestamp: { seconds: 1_700_000_000n },
    symbol: '',
    description: '',
    quantity: undefined,
    price: undefined,
    ...over,
  };
}

/** Map one transaction through the store and return its row. */
async function rowFor(over: Record<string, unknown>) {
  listTransactions.mockResolvedValue({ transactions: [txn(over)], pagination: { hasNext: false } });
  await useActivityStore.getState().fetch();
  return useActivityStore.getState().rows[0];
}

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useActivityStore.setState({
    rows: [],
    loading: false,
    loadingMore: false,
    error: null,
    page: 1,
    hasMore: false,
  });
});

describe('row mapping', () => {
  it('signs a deposit positive and a withdrawal negative', async () => {
    const deposit = await rowFor({ type: TransactionType.DEPOSIT });
    expect(deposit).toMatchObject({ kind: 'deposit', group: 'funding', signed: 100 });

    const withdrawal = await rowFor({ type: TransactionType.WITHDRAWAL });
    expect(withdrawal).toMatchObject({ kind: 'withdrawal', group: 'funding', signed: -100 });
  });

  it('reads an allocation as cash leaving and a release as cash returning', async () => {
    const allocation = await rowFor({
      type: TransactionType.TRANSFER_OUT,
      description: 'Momentum sleeve',
    });
    expect(allocation).toMatchObject({ kind: 'allocation', group: 'allocations', signed: -100 });

    const release = await rowFor({
      type: TransactionType.TRANSFER_IN,
      description: 'Released to Unallocated',
    });
    expect(release).toMatchObject({ kind: 'release', group: 'allocations', signed: 100 });
  });

  it('classifies a release by the sleeve named, not the transfer direction', async () => {
    // Both directions appear for both cases; only the description disambiguates.
    const row = await rowFor({ type: TransactionType.TRANSFER_OUT, description: 'to unallocated' });

    expect(row.kind).toBe('release');
  });

  it.each([
    [TransactionType.BUY, 'buy', 'Buy AAPL'],
    [TransactionType.SELL, 'sell', 'Sell AAPL'],
  ])('labels a %s trade with its symbol', async (type, kind, label) => {
    const row = await rowFor({
      type,
      symbol: 'AAPL',
      quantity: { value: '10' },
      price: { value: '150' },
    });

    expect(row.kind).toBe(kind);
    expect(row.group).toBe('trades');
    expect(row.label).toBe(label);
    expect(row.sublabel).toContain('10 @');
    // A trade moves holdings, not cash: it must not sign the running balance.
    expect(row.signed).toBe(0);
  });

  it('falls back to the symbol when a trade carries no quantity or price', async () => {
    const row = await rowFor({ type: TransactionType.BUY, symbol: 'MSFT' });

    expect(row.sublabel).toBe('MSFT');
  });

  it.each([
    [TransactionType.DIVIDEND, 'dividend'],
    [TransactionType.INTEREST, 'interest'],
    [TransactionType.FEE, 'fee'],
  ])('maps %s to its own kind with no cash sign', async (type, kind) => {
    const row = await rowFor({ type, symbol: 'SPY' });

    expect(row.kind).toBe(kind);
    expect(row.signed).toBe(0);
  });

  it('maps an unrecognised type to a neutral row instead of dropping it', async () => {
    const row = await rowFor({ type: 9999 });

    expect(row).toMatchObject({ kind: 'other', label: 'Activity', signed: 0 });
  });

  it('converts the proto timestamp to a real date', async () => {
    const row = await rowFor({ timestamp: { seconds: 1_700_000_000n } });

    expect(row.at.getTime()).toBe(1_700_000_000 * 1000);
  });

  it('falls back to the epoch when a row carries no timestamp', async () => {
    const row = await rowFor({ timestamp: undefined });

    expect(row.at.getTime()).toBe(0);
  });
});

describe('paging', () => {
  it('replaces the list on fetch and records whether more pages exist', async () => {
    listTransactions.mockResolvedValue({
      transactions: [txn({ id: 'a' })],
      pagination: { hasNext: true },
    });

    await useActivityStore.getState().fetch();

    const state = useActivityStore.getState();
    expect(state.rows.map((r) => r.id)).toEqual(['a']);
    expect(state.hasMore).toBe(true);
    expect(state.page).toBe(1);
  });

  it('appends the next page and advances the cursor', async () => {
    listTransactions.mockResolvedValueOnce({
      transactions: [txn({ id: 'a' })],
      pagination: { hasNext: true },
    });
    await useActivityStore.getState().fetch();

    listTransactions.mockResolvedValueOnce({
      transactions: [txn({ id: 'b' })],
      pagination: { hasNext: false },
    });
    await useActivityStore.getState().loadMore();

    const state = useActivityStore.getState();
    expect(state.rows.map((r) => r.id)).toEqual(['a', 'b']);
    expect(state.page).toBe(2);
    expect(state.hasMore).toBe(false);
    expect(listTransactions.mock.calls[1][0].pagination.page).toBe(2);
  });

  it('does not page past the end', async () => {
    useActivityStore.setState({ hasMore: false });

    await useActivityStore.getState().loadMore();

    expect(listTransactions).not.toHaveBeenCalled();
  });

  it('does not issue a second page request while one is in flight', async () => {
    useActivityStore.setState({ hasMore: true, loadingMore: true });

    await useActivityStore.getState().loadMore();

    expect(listTransactions).not.toHaveBeenCalled();
  });

  it('keeps the rows already shown when loading more fails', async () => {
    listTransactions.mockResolvedValueOnce({
      transactions: [txn({ id: 'a' })],
      pagination: { hasNext: true },
    });
    await useActivityStore.getState().fetch();

    listTransactions.mockRejectedValueOnce(new Error('page failed'));
    await useActivityStore.getState().loadMore();

    const state = useActivityStore.getState();
    expect(state.rows.map((r) => r.id)).toEqual(['a']);
    expect(state.loadingMore).toBe(false);
    expect(state.error).toBe('page failed');
  });

  it('reports a failed first load', async () => {
    listTransactions.mockRejectedValue(new Error('down'));

    await useActivityStore.getState().fetch();

    expect(useActivityStore.getState().loading).toBe(false);
    expect(useActivityStore.getState().error).toBe('down');
  });
});
