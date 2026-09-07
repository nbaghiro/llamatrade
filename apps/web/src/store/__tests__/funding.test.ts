/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listAlpacaCredentials, getOrCreateAccount, depositFunds } = vi.hoisted(() => ({
  listAlpacaCredentials: vi.fn(),
  getOrCreateAccount: vi.fn(),
  depositFunds: vi.fn(),
}));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  authClient: { listAlpacaCredentials },
  ledgerClient: { getOrCreateAccount, depositFunds },
  getTenantContext: () => tenantContext,
}));

import { ConnectError } from '@connectrpc/connect';
import { SleeveType } from '@llamatrade/core/proto/ledger_pb';
import { useFundingStore } from '@llamatrade/core/stores/funding';

const INITIAL = useFundingStore.getState();

/** A sleeve whose free cash is balance − reserved. */
function sleeve(type: SleeveType, balance: string, reserved = '0') {
  return { type, cash: { balance: { value: balance }, reserved: { value: reserved } } };
}

function cred(id: string, { isPaper = true, isActive = true } = {}) {
  return { id, isPaper, isActive };
}

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useFundingStore.setState({
    accountId: null,
    paperCredentialId: null,
    credentials: [],
    unallocatedCash: 0,
    resolving: false,
    resolved: false,
    submitting: false,
    error: null,
    hasAccount: INITIAL.hasAccount,
    resolveAccount: INITIAL.resolveAccount,
    addFunds: INITIAL.addFunds,
    clearError: INITIAL.clearError,
  });
});

describe('resolveAccount', () => {
  it('prefers an active paper credential and reads Unallocated free cash', async () => {
    listAlpacaCredentials.mockResolvedValue({
      credentials: [cred('live-1', { isPaper: false }), cred('paper-1')],
    });
    getOrCreateAccount.mockResolvedValue({
      account: { id: 'acct-1' },
      baseSleeves: [
        sleeve(SleeveType.UNALLOCATED, '1000', '250'),
        sleeve(SleeveType.STRATEGY, '9999'),
      ],
    });

    await useFundingStore.getState().resolveAccount();

    const state = useFundingStore.getState();
    expect(state.paperCredentialId).toBe('paper-1');
    expect(state.accountId).toBe('acct-1');
    // Free cash is balance − reserved, and only the Unallocated sleeve counts.
    expect(state.unallocatedCash).toBe(750);
    expect(state.resolved).toBe(true);
    expect(state.hasAccount()).toBe(true);
  });

  it('falls back to any active credential when none is paper', async () => {
    listAlpacaCredentials.mockResolvedValue({
      credentials: [cred('live-1', { isPaper: false })],
    });
    getOrCreateAccount.mockResolvedValue({ account: { id: 'acct-2' }, baseSleeves: [] });

    await useFundingStore.getState().resolveAccount();

    expect(useFundingStore.getState().paperCredentialId).toBe('live-1');
  });

  it('resolves with no account when the tenant has no active credential', async () => {
    listAlpacaCredentials.mockResolvedValue({
      credentials: [cred('stale', { isActive: false })],
    });

    await useFundingStore.getState().resolveAccount();

    const state = useFundingStore.getState();
    expect(state.resolved).toBe(true);
    expect(state.accountId).toBeNull();
    expect(state.hasAccount()).toBe(false);
    expect(getOrCreateAccount).not.toHaveBeenCalled();
  });

  it('surfaces a ConnectError message and still finishes resolving', async () => {
    listAlpacaCredentials.mockRejectedValue(new ConnectError('ledger unavailable'));

    await useFundingStore.getState().resolveAccount();

    const state = useFundingStore.getState();
    expect(state.resolving).toBe(false);
    expect(state.resolved).toBe(true);
    expect(state.error).toContain('ledger unavailable');
  });

  it('does not issue a second call while one is in flight', async () => {
    useFundingStore.setState({ resolving: true });

    await useFundingStore.getState().resolveAccount();

    expect(listAlpacaCredentials).not.toHaveBeenCalled();
  });
});

describe('addFunds', () => {
  beforeEach(() => {
    useFundingStore.setState({ accountId: 'acct-1', paperCredentialId: 'paper-1', resolved: true });
  });

  it('deposits and returns the new free balance', async () => {
    depositFunds.mockResolvedValue({ unallocated: sleeve(SleeveType.UNALLOCATED, '1500', '100') });

    const free = await useFundingStore.getState().addFunds(500);

    expect(free).toBe(1400);
    expect(useFundingStore.getState().unallocatedCash).toBe(1400);
    expect(useFundingStore.getState().submitting).toBe(false);
  });

  it('sends a unique requestId so a retried deposit cannot double-credit', async () => {
    depositFunds.mockResolvedValue({ unallocated: sleeve(SleeveType.UNALLOCATED, '100') });

    await useFundingStore.getState().addFunds(50);
    await useFundingStore.getState().addFunds(50);

    const [first, second] = depositFunds.mock.calls.map((c) => c[0]);
    // The server rejects a deposit with no requestId; each retry needs its own.
    expect(first.requestId).toBeTruthy();
    expect(second.requestId).toBeTruthy();
    expect(first.requestId).not.toBe(second.requestId);
  });

  it('sends the amount as a cents-precise decimal string', async () => {
    depositFunds.mockResolvedValue({ unallocated: sleeve(SleeveType.UNALLOCATED, '0') });

    await useFundingStore.getState().addFunds(1234.5);

    expect(depositFunds.mock.calls[0][0].amount).toEqual({ value: '1234.50' });
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    'refuses a non-positive or non-finite amount (%s)',
    async (amount) => {
      const result = await useFundingStore.getState().addFunds(amount);

      expect(result).toBeNull();
      expect(depositFunds).not.toHaveBeenCalled();
      expect(useFundingStore.getState().error).toBeTruthy();
    }
  );

  it('resolves the account first when one is not loaded yet', async () => {
    useFundingStore.setState({ accountId: null });
    listAlpacaCredentials.mockResolvedValue({ credentials: [cred('paper-1')] });
    getOrCreateAccount.mockResolvedValue({ account: { id: 'acct-9' }, baseSleeves: [] });
    depositFunds.mockResolvedValue({ unallocated: sleeve(SleeveType.UNALLOCATED, '10') });

    await useFundingStore.getState().addFunds(10);

    expect(getOrCreateAccount).toHaveBeenCalled();
    expect(depositFunds.mock.calls[0][0].accountId).toBe('acct-9');
  });

  it('refuses to deposit when no account can be resolved', async () => {
    useFundingStore.setState({ accountId: null });
    listAlpacaCredentials.mockResolvedValue({ credentials: [] });

    const result = await useFundingStore.getState().addFunds(100);

    expect(result).toBeNull();
    expect(depositFunds).not.toHaveBeenCalled();
    expect(useFundingStore.getState().error).toMatch(/connect/i);
  });

  it('reports a failed deposit without changing the cached balance', async () => {
    useFundingStore.setState({ unallocatedCash: 42 });
    depositFunds.mockRejectedValue(new ConnectError('insufficient'));

    const result = await useFundingStore.getState().addFunds(100);

    expect(result).toBeNull();
    expect(useFundingStore.getState().unallocatedCash).toBe(42);
    expect(useFundingStore.getState().submitting).toBe(false);
    expect(useFundingStore.getState().error).toContain('insufficient');
  });

  it('clearError resets the message', () => {
    useFundingStore.setState({ error: 'boom' });

    useFundingStore.getState().clearError();

    expect(useFundingStore.getState().error).toBeNull();
  });
});
