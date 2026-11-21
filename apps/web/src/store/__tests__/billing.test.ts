/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import {
  PLAN_TIERS,
  PLAN_TIER_BY_KEY,
  tierPricePerMonth,
  tierPriceTotal,
} from '@llamatrade/core/billing/planTiers';
import { meterState, usagePeriod } from '@llamatrade/core/billing/usage';
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
    loaded: {},
    errors: {},
  });
  billing.listPlans.mockResolvedValue({ plans: [{ id: 'free' }, { id: 'pro' }] });
  billing.getSubscription.mockResolvedValue({ subscription: SUB });
  billing.listPaymentMethods.mockResolvedValue({ paymentMethods: [{ id: 'pm-1' }] });
  billing.listInvoices.mockResolvedValue({ invoices: [{ id: 'inv-1' }] });
  billing.createSubscription.mockResolvedValue({ subscription: SUB });
  billing.updateSubscription.mockResolvedValue({ subscription: SUB });
  billing.cancelSubscription.mockResolvedValue({
    subscription: { ...SUB, cancelAtPeriodEnd: true },
  });
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
    const client =
      name === 'cancelSubscription' ? billing.cancelSubscription : billing.resumeSubscription;
    client.mockRejectedValue(new ConnectError('server said no'));

    await expect(run()).rejects.toThrow();
    expect(useBillingStore.getState().loading).toBe(false);
    expect(useBillingStore.getState().error).toContain('server said no');
  });
});

const at = (y: number, m: number, d: number) => ({
  seconds: BigInt(Math.floor(new Date(y, m, d, 12).getTime() / 1000)),
  nanos: 0,
});

describe('fetchUsageCounts', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 16, 9));
    usage.listStrategies.mockResolvedValue({ pagination: { totalItems: 7 }, strategies: [] });
    usage.listBacktests.mockResolvedValue({
      pagination: { totalItems: 12 },
      backtests: [
        { createdAt: at(2026, 10, 1) },
        { createdAt: at(2026, 10, 15) },
        { createdAt: at(2026, 9, 31) },
        {},
      ],
    });
    usage.listStrategyPerformance.mockResolvedValue({
      strategies: [
        { status: ExecutionStatus.RUNNING, mode: ExecutionMode.LIVE },
        { status: ExecutionStatus.RUNNING, mode: ExecutionMode.LIVE },
        { status: ExecutionStatus.RUNNING, mode: ExecutionMode.PAPER },
        { status: ExecutionStatus.STOPPED, mode: ExecutionMode.LIVE },
      ],
    });
    usage.listSessions.mockResolvedValue({
      sessions: [
        { messageCount: 3, lastActivityAt: at(2026, 10, 10) },
        { messageCount: 4, createdAt: at(2026, 10, 2) },
        { messageCount: 50, lastActivityAt: at(2026, 9, 20) },
      ],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('derives all four meters from the real product surfaces', async () => {
    await useBillingStore.getState().fetchUsageCounts();

    expect(useBillingStore.getState().usageCounts).toEqual({
      strategies: 7,
      backtests: 2, // only this calendar month, whatever the all-time total says
      liveSessions: 2, // only running live executions count
      copilotMessages: 7, // conversations active this month, falling back to createdAt
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

describe('per-panel load state', () => {
  it('marks each read loaded on success so panels can tell empty from loading', async () => {
    expect(useBillingStore.getState().loaded).toEqual({});

    await useBillingStore.getState().fetchInvoices();

    expect(useBillingStore.getState().loaded.invoices).toBe(true);
    expect(useBillingStore.getState().loaded.paymentMethods).toBeUndefined();
    expect(useBillingStore.getState().errors.invoices).toBeUndefined();
  });

  it('keeps a failure on its own panel and clears it after a good retry', async () => {
    billing.listInvoices.mockRejectedValueOnce(new ConnectError('billing down'));

    await useBillingStore.getState().fetchInvoices();
    await useBillingStore.getState().fetchPaymentMethods();

    let state = useBillingStore.getState();
    expect(state.loaded.invoices).toBe(true);
    expect(state.errors.invoices).toContain('billing down');
    expect(state.errors.paymentMethods).toBeUndefined();

    await useBillingStore.getState().fetchInvoices();
    state = useBillingStore.getState();
    expect(state.errors.invoices).toBeUndefined();
    expect(state.invoices).toHaveLength(1);
  });

  it('counts a missing subscription as loaded, not failed', async () => {
    billing.getSubscription.mockRejectedValue(new ConnectError('none', Code.NotFound));

    await useBillingStore.getState().fetchSubscription();

    const state = useBillingStore.getState();
    expect(state.loaded.subscription).toBe(true);
    expect(state.errors.subscription).toBeUndefined();
    expect(state.subscription).toBeNull();
  });
});

describe('plan tiers', () => {
  it('lists the three plans low to high with the beta prices', () => {
    expect(PLAN_TIERS.map((t) => [t.key, t.monthlyPrice])).toEqual([
      ['free', 0],
      ['pro', 49],
      ['enterprise', 199],
    ]);
  });

  it('applies the yearly discount per month and in total', () => {
    const pro = PLAN_TIER_BY_KEY.pro;
    expect(tierPricePerMonth(pro, false)).toBe(49);
    expect(tierPricePerMonth(pro, true)).toBe(41);
    expect(tierPriceTotal(pro, true)).toBe(488);
    expect(tierPricePerMonth(PLAN_TIER_BY_KEY.free, true)).toBe(0);
  });
});

describe('usage maths', () => {
  it('spans the calendar month containing now', () => {
    const p = usagePeriod(new Date(2026, 1, 14, 18));
    expect(p.start).toEqual(new Date(2026, 1, 1));
    expect(p.end).toEqual(new Date(2026, 1, 28));
  });

  it.each([
    [6, 10, { fraction: 0.6, atLimit: false, unlimited: false, note: '4 remaining' }],
    [10, 10, { fraction: 1, atLimit: true, unlimited: false, note: 'At the limit' }],
    [14, 10, { fraction: 1, atLimit: true, unlimited: false, note: 'At the limit' }],
    [1500, -1, { fraction: 0, atLimit: false, unlimited: true, note: 'Unlimited' }],
    [0, 0, { fraction: 0, atLimit: false, unlimited: false, note: 'Not included' }],
    [-3, 10, { fraction: 0, atLimit: false, unlimited: false, note: '10 remaining' }],
    [214, 2000, { fraction: 0.107, atLimit: false, unlimited: false, note: '1,786 remaining' }],
  ])('meters %s of %s', (used, limit, expected) => {
    expect(meterState(used, limit)).toEqual(expected);
  });
});
