/**
 * Billing read store — the real backend, same RPCs the web app uses
 * (apps/web/src/store/billing.ts): GetSubscription + GetUsage + ListPaymentMethods
 * + ListInvoices. Read-only: subscribe/checkout/cancel stay on the desktop.
 *
 * App-local for now (mirrors auth/agent/portfolio); a future slice can lift the
 * read side into @llamatrade/core alongside the strategies store.
 */
import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import type { Invoice, PaymentMethod, Subscription, Usage } from '@llamatrade/core/proto/billing_pb';
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
  loading: boolean;
  refreshing: boolean;
  loaded: boolean;
  error: string | null;
  fetch: (opts?: { refresh?: boolean }) => Promise<void>;
}

export const useBillingStore = create<BillingState>((set) => ({
  subscription: null,
  usage: null,
  usageLimit: null,
  paymentMethods: [],
  invoices: [],
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
}));
