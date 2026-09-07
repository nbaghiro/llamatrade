/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const billing = vi.hoisted(() => ({
  listPlans: vi.fn(),
  getSubscription: vi.fn(),
  listPaymentMethods: vi.fn(),
  listInvoices: vi.fn(),
  createSubscription: vi.fn(),
  updateSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
  resumeSubscription: vi.fn(),
}));
const usage = vi.hoisted(() => ({
  listStrategies: vi.fn(),
  listBacktests: vi.fn(),
  listStrategyPerformance: vi.fn(),
  listSessions: vi.fn(),
}));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  billingClient: billing,
  strategyClient: { listStrategies: usage.listStrategies },
  backtestClient: { listBacktests: usage.listBacktests },
  portfolioClient: { listStrategyPerformance: usage.listStrategyPerformance },
  agentClient: { listSessions: usage.listSessions },
  getTenantContext: () => tenantContext,
}));

import { Code, ConnectError } from '@connectrpc/connect';
import { BillingInterval } from '@llamatrade/core/proto/billing_pb';
import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { useBillingStore } from '@llamatrade/core/stores/billing';

const SUB = { id: 'sub-1', planId: 'pro' };

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useBillingStore.setState({
    plans: [],
    subscription: null,
    paymentMethods: [],
    invoices: [],
    usageCounts: null,
    loading: false,
    error: null,
  });
  billing.listPlans.mockResolvedValue({ plans: [{ id: 'free' }, { id: 'pro' }] });
  billing.getSubscription.mockResolvedValue({ subscription: SUB });
  billing.listPaymentMethods.mockResolvedValue({ paymentMethods: [{ id: 'pm-1' }] });
  billing.listInvoices.mockResolvedValue({ invoices: [{ id: 'inv-1' }] });
  billing.createSubscription.mockResolvedValue({ subscription: SUB });
  billing.updateSubscription.mockResolvedValue({ subscription: SUB });
  billing.cancelSubscription.mockResolvedValue({ subscription: { ...SUB, cancelAtPeriodEnd: true } });
  billing.resumeSubscription.mockResolvedValue({ subscription: SUB });
});

describe('reads', () => {
  it('loads plans, payment methods and invoices', async () => {
    await useBillingStore.getState().fetchPlans();
    await useBillingStore.getState().fetchPaymentMethods();
    await useBillingStore.getState().fetchInvoices();

    const state = useBillingStore.getState();
    expect(state.plans).toHaveLength(2);
    expect(state.paymentMethods).toHaveLength(1);
    expect(state.invoices).toHaveLength(1);
    expect(state.loading).toBe(false);
  });

  it('treats NOT_FOUND as "no subscription", not an error', async () => {
    billing.getSubscription.mockRejectedValue(new ConnectError('none', Code.NotFound));

    await useBillingStore.getState().fetchSubscription();

    const state = useBillingStore.getState();
    expect(state.subscription).toBeNull();
    expect(state.error).toBeNull();
    expect(state.loading).toBe(false);
  });

  it('surfaces any other subscription failure', async () => {
    billing.getSubscription.mockRejectedValue(new ConnectError('boom', Code.Internal));

    await useBillingStore.getState().fetchSubscription();

    expect(useBillingStore.getState().error).toContain('boom');
  });

  it.each([
    ['fetchPlans', () => useBillingStore.getState().fetchPlans(), billing.listPlans],
    [
      'fetchPaymentMethods',
      () => useBillingStore.getState().fetchPaymentMethods(),
      billing.listPaymentMethods,
    ],
    ['fetchInvoices', () => useBillingStore.getState().fetchInvoices(), billing.listInvoices],
  ])('%s clears loading on failure', async (_name, run, client) => {
    client.mockRejectedValue(new Error('down'));

    await run();

    expect(useBillingStore.getState().loading).toBe(false);
    expect(useBillingStore.getState().error).toBe('down');
  });
});

describe('mutations', () => {
  it('creates a subscription and caches it', async () => {
    const sub = await useBillingStore
      .getState()
      .createSubscription('pro', BillingInterval.MONTHLY, 'pm-1');

    expect(sub).toEqual(SUB);
    expect(useBillingStore.getState().subscription).toEqual(SUB);
    expect(billing.createSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ planId: 'pro', paymentMethodId: 'pm-1' })
    );
  });

  it('rejects a create that returns no subscription rather than caching undefined', async () => {
    billing.createSubscription.mockResolvedValue({ subscription: undefined });

    await expect(
      useBillingStore.getState().createSubscription('pro', BillingInterval.MONTHLY)
    ).rejects.toThrow(/No subscription returned/);
    expect(useBillingStore.getState().subscription).toBeNull();
    expect(useBillingStore.getState().loading).toBe(false);
  });

  it('rethrows a failed create so the page can react, and records the message', async () => {
    billing.createSubscription.mockRejectedValue(new ConnectError('card declined'));

    await expect(
      useBillingStore.getState().createSubscription('pro', BillingInterval.MONTHLY)
    ).rejects.toThrow();
    expect(useBillingStore.getState().error).toContain('card declined');
    expect(useBillingStore.getState().loading).toBe(false);
  });

  it('updates the plan and caches the returned subscription', async () => {
    await useBillingStore.getState().updateSubscription('pro', BillingInterval.YEARLY, true);

    expect(billing.updateSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ planId: 'pro', interval: BillingInterval.YEARLY, prorate: true })
    );
    expect(useBillingStore.getState().subscription).toEqual(SUB);
  });

  it('cancels at period end by default', async () => {
    await useBillingStore.getState().cancelSubscription();

    expect(billing.cancelSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ cancelImmediately: false })
    );
    expect(useBillingStore.getState().subscription?.cancelAtPeriodEnd).toBe(true);
  });

  it('passes an immediate cancellation through with its reason', async () => {
    await useBillingStore.getState().cancelSubscription(true, 'too expensive');

    expect(billing.cancelSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ cancelImmediately: true, reason: 'too expensive' })
    );
  });

  it('resumes and caches the restored subscription', async () => {
    await useBillingStore.getState().resumeSubscription();

    expect(useBillingStore.getState().subscription).toEqual(SUB);
  });

  it.each([
    ['cancelSubscription', () => useBillingStore.getState().cancelSubscription()],
    ['resumeSubscription', () => useBillingStore.getState().resumeSubscription()],
  ])('%s rethrows on failure', async (name, run) => {
    const client = name === 'cancelSubscription' ? billing.cancelSubscription : billing.resumeSubscription;
    client.mockRejectedValue(new ConnectError('server said no'));

    await expect(run()).rejects.toThrow();
    expect(useBillingStore.getState().loading).toBe(false);
    expect(useBillingStore.getState().error).toContain('server said no');
  });
});

describe('fetchUsageCounts', () => {
  beforeEach(() => {
    usage.listStrategies.mockResolvedValue({ pagination: { totalItems: 7 }, strategies: [] });
    usage.listBacktests.mockResolvedValue({ pagination: { totalItems: 12 }, backtests: [] });
    usage.listStrategyPerformance.mockResolvedValue({
      strategies: [
        { status: ExecutionStatus.RUNNING },
        { status: ExecutionStatus.RUNNING },
        { status: ExecutionStatus.STOPPED },
      ],
    });
    usage.listSessions.mockResolvedValue({
      sessions: [{ messageCount: 3 }, { messageCount: 4 }],
    });
  });

  it('derives all four meters from the real product surfaces', async () => {
    await useBillingStore.getState().fetchUsageCounts();

    expect(useBillingStore.getState().usageCounts).toEqual({
      strategies: 7,
      backtests: 12,
      liveSessions: 2, // only RUNNING executions count
      copilotMessages: 7, // summed across sessions
    });
  });

  it('falls back to the row count when pagination carries no total', async () => {
    usage.listStrategies.mockResolvedValue({ strategies: [{}, {}, {}] });

    await useBillingStore.getState().fetchUsageCounts();

    expect(useBillingStore.getState().usageCounts?.strategies).toBe(3);
  });

  it('degrades a failed meter to zero instead of losing the others', async () => {
    usage.listBacktests.mockRejectedValue(new ConnectError('backtest down'));

    await useBillingStore.getState().fetchUsageCounts();

    expect(useBillingStore.getState().usageCounts).toEqual({
      strategies: 7,
      backtests: 0,
      liveSessions: 2,
      copilotMessages: 7,
    });
  });

  it('reports no usage at all when signed out', async () => {
    tenantContext = undefined;

    await useBillingStore.getState().fetchUsageCounts();

    expect(useBillingStore.getState().usageCounts).toBeNull();
    expect(usage.listStrategies).not.toHaveBeenCalled();
  });
});
