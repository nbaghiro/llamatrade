/**
 * Billing store — the real backend, same RPCs the web app uses
 * (apps/web/src/store/billing.ts): GetSubscription + GetUsage + ListPaymentMethods
 * + ListInvoices + ListPlans. Reads are the main surface; the only write is a
 * free downgrade (no payment) — paid upgrades/checkout stay on the desktop (IAP).
 *
 * App-local for now (mirrors auth/agent/portfolio); a future slice can lift this
 * into @llamatrade/core alongside the strategies store.
 */
import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import type { Invoice, PaymentMethod, Plan, Subscription, Usage } from '@llamatrade/core/proto/billing_pb';
import { BillingInterval, PlanTier } from '@llamatrade/core/proto/billing_pb';

import { billingClient } from '../net/clients';
import { tenantContext } from './auth';

function errorMessage(e: unknown): string {
  if (e instanceof ConnectError) return e.rawMessage || e.message;
  return e instanceof Error ? e.message : 'Something went wrong';
}

interface BillingState {
  subscription: Subscription | null;
  usage: Usage | null;
  usageLimit: Usage | null;
  paymentMethods: PaymentMethod[];
  invoices: Invoice[];
  plans: Plan[];
  loading: boolean;
  refreshing: boolean;
  loaded: boolean;
  error: string | null;
  fetch: (opts?: { refresh?: boolean }) => Promise<void>;
  fetchPlans: () => Promise<void>;
  /** Switch to the Free plan (no payment). Paid changes go through the web. */
  downgradeToFree: () => Promise<void>;
}

export const useBillingStore = create<BillingState>((set, get) => ({
  subscription: null,
  usage: null,
  usageLimit: null,
  paymentMethods: [],
  invoices: [],
  plans: [],
  loading: false,
  refreshing: false,
  loaded: false,
  error: null,

  fetch: async (opts) => {
    const context = tenantContext();
    if (!context) {
      set({ error: 'Not signed in.', loading: false, refreshing: false });
      return;
    }
    set(opts?.refresh ? { refreshing: true, error: null } : { loading: true, error: null });
    try {
      // Each read is independent; a missing subscription or empty history must not
      // blank the whole screen, so failures degrade per-section rather than throw.
      const [sub, usage, methods, invoices] = await Promise.all([
        billingClient.getSubscription({ context }).then((r) => r.subscription ?? null).catch(() => null),
        billingClient.getUsage({ context, periodId: '' }).catch(() => null),
        billingClient.listPaymentMethods({ context }).then((r) => r.paymentMethods).catch(() => []),
        billingClient
          .listInvoices({ context, pagination: { page: 1, pageSize: 12 } })
          .then((r) => r.invoices)
          .catch(() => []),
      ]);
      set({
        subscription: sub,
        usage: usage?.usage ?? null,
        usageLimit: usage?.limit ?? null,
        paymentMethods: methods,
        invoices,
        loading: false,
        refreshing: false,
        loaded: true,
      });
    } catch (e) {
      set({ error: errorMessage(e), loading: false, refreshing: false });
    }
  },

  fetchPlans: async () => {
    const context = tenantContext();
    if (!context) return;
    try {
      const res = await billingClient.listPlans({ context });
      set({ plans: res.plans });
    } catch {
      // non-fatal: the comparison grid falls back to the static plan-tier config
    }
  },

  downgradeToFree: async () => {
    const context = tenantContext();
    if (!context) throw new Error('Not signed in.');
    const free = get().plans.find((p) => p.tier === PlanTier.FREE);
    if (!free) throw new Error('The Free plan is unavailable here — manage your plan on the web.');
    const res = get().subscription
      ? await billingClient.updateSubscription({
          context,
          planId: free.id,
          interval: BillingInterval.MONTHLY,
          prorate: true,
        })
      : await billingClient.createSubscription({
          context,
          planId: free.id,
          interval: BillingInterval.MONTHLY,
          paymentMethodId: '',
          promoCode: '',
        });
    set({ subscription: res.subscription ?? get().subscription });
  },
}));
