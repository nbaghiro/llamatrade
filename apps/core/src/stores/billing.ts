/**
 * Billing state management with Zustand.
 *
 * All reads/writes thread the real tenant context (see getTenantContext). Usage
 * counts are derived from the live product surfaces (strategies, this month's
 * backtests, running executions and Copilot conversations active this month),
 * measured against the current plan's limits in billing/planTiers.ts.
 */

import { Code, ConnectError } from "@connectrpc/connect";
import { create, type StoreApi } from "zustand";

import { AgentSessionStatus } from "@llamatrade/core/proto/agent_pb";
import {
  BillingInterval,
  type Invoice,
  type PaymentMethod,
  type Plan,
  type Subscription,
} from "@llamatrade/core/proto/billing_pb";
import {
  ExecutionMode,
  ExecutionStatus,
  type Timestamp,
} from "@llamatrade/core/proto/common_pb";
import { usagePeriod } from "../billing/usage";
import { errorMessage } from "../errors";
import {
  agentClient,
  backtestClient,
  billingClient,
  portfolioClient,
  strategyClient,
} from "../net";

import { getTenantContext } from "../net";

/** Real usage counts derived from the product APIs. */
export interface UsageCounts {
  strategies: number;
  /** Backtests created since the start of the calendar month. */
  backtests: number;
  liveSessions: number;
  /** Messages in Copilot conversations active since the start of the calendar month. */
  copilotMessages: number;
}

export type BillingResource =
  | "plans"
  | "subscription"
  | "paymentMethods"
  | "invoices";

interface BillingState {
  // State
  plans: Plan[];
  subscription: Subscription | null;
  paymentMethods: PaymentMethod[];
  invoices: Invoice[];
  usageCounts: UsageCounts | null;
  loading: boolean;
  error: string | null;
  /** Which reads have finished at least once, so panels can tell loading from empty. */
  loaded: Partial<Record<BillingResource, boolean>>;
  /** The last failure per read, so one panel can fail without the others. */
  errors: Partial<Record<BillingResource, string>>;

  // Actions
  fetchPlans: () => Promise<void>;
  fetchSubscription: () => Promise<void>;
  fetchPaymentMethods: () => Promise<void>;
  fetchInvoices: () => Promise<void>;
  fetchUsageCounts: () => Promise<void>;
  createSubscription: (
    planId: string,
    interval: BillingInterval,
    paymentMethodId?: string,
  ) => Promise<Subscription>;
  updateSubscription: (
    planId: string,
    interval?: BillingInterval,
    prorate?: boolean,
  ) => Promise<Subscription>;
  cancelSubscription: (
    cancelImmediately?: boolean,
    reason?: string,
  ) => Promise<void>;
  resumeSubscription: () => Promise<void>;
  setSubscription: (subscription: Subscription | null) => void;
  clearError: () => void;
}

type SetBilling = StoreApi<BillingState>["setState"];

function succeed(
  set: SetBilling,
  resource: BillingResource,
  patch: Partial<BillingState>,
): void {
  set((s) => ({
    ...patch,
    loading: false,
    loaded: { ...s.loaded, [resource]: true },
    errors: { ...s.errors, [resource]: undefined },
  }));
}

function fail(
  set: SetBilling,
  resource: BillingResource,
  error: unknown,
  fallback: string,
): void {
  const message = error instanceof Error ? errorMessage(error) : fallback;
  set((s) => ({
    error: message,
    loading: false,
    loaded: { ...s.loaded, [resource]: true },
    errors: { ...s.errors, [resource]: message },
  }));
}

const tsMs = (ts: Timestamp | undefined): number =>
  ts ? Number(ts.seconds) * 1000 + Math.floor(ts.nanos / 1_000_000) : 0;

export const useBillingStore = create<BillingState>((set) => ({
  // Initial state
  plans: [],
  subscription: null,
  paymentMethods: [],
  invoices: [],
  usageCounts: null,
  loading: false,
  error: null,
  loaded: {},
  errors: {},

  // Actions
  fetchPlans: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listPlans({
        context: getTenantContext(),
      });
      succeed(set, "plans", { plans: response.plans });
    } catch (error) {
      fail(set, "plans", error, "Failed to fetch plans");
    }
  },

  fetchSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.getSubscription({
        context: getTenantContext(),
      });
      succeed(set, "subscription", {
        subscription: response.subscription ?? null,
      });
    } catch (error) {
      // NOT_FOUND means no subscription exists - this is normal for new users
      if (error instanceof ConnectError && error.code === Code.NotFound) {
        succeed(set, "subscription", { subscription: null });
        return;
      }
      fail(set, "subscription", error, "Failed to fetch subscription");
    }
  },

  fetchPaymentMethods: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listPaymentMethods({
        context: getTenantContext(),
      });
      succeed(set, "paymentMethods", {
        paymentMethods: response.paymentMethods,
      });
    } catch (error) {
      fail(set, "paymentMethods", error, "Failed to fetch payment methods");
    }
  },

  fetchInvoices: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listInvoices({
        context: getTenantContext(),
      });
      succeed(set, "invoices", { invoices: response.invoices });
    } catch (error) {
      fail(set, "invoices", error, "Failed to fetch invoices");
    }
  },

  // Derive the four usage meters from the real product surfaces; each is independent and degrades to 0 on failure.
  fetchUsageCounts: async () => {
    const context = getTenantContext();
    if (!context) {
      set({ usageCounts: null });
      return;
    }
    const since = usagePeriod(new Date()).start.getTime();

    const [strategies, backtests, liveSessions, copilotMessages] =
      await Promise.all([
        strategyClient
          .listStrategies({ context, pagination: { page: 1, pageSize: 100 } })
          .then((r) => r.pagination?.totalItems ?? r.strategies.length)
          .catch(() => 0),
        backtestClient
          .listBacktests({
            context,
            strategyId: "",
            pagination: { page: 1, pageSize: 100 },
          })
          .then(
            (r) => r.backtests.filter((b) => tsMs(b.createdAt) >= since).length,
          )
          .catch(() => 0),
        portfolioClient
          .listStrategyPerformance({
            context,
            pagination: { page: 1, pageSize: 100 },
          })
          .then(
            (r) =>
              r.strategies.filter(
                (s) =>
                  s.status === ExecutionStatus.RUNNING &&
                  s.mode === ExecutionMode.LIVE,
              ).length,
          )
          .catch(() => 0),
        agentClient
          .listSessions({
            context,
            statusFilter: AgentSessionStatus.UNSPECIFIED,
            pagination: { page: 1, pageSize: 100 },
          })
          .then((r) =>
            r.sessions
              .filter((s) => tsMs(s.lastActivityAt ?? s.createdAt) >= since)
              .reduce((sum, s) => sum + s.messageCount, 0),
          )
          .catch(() => 0),
      ]);

    set({
      usageCounts: { strategies, backtests, liveSessions, copilotMessages },
    });
  },

  createSubscription: async (planId, interval, paymentMethodId) => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.createSubscription({
        context: getTenantContext(),
        planId,
        interval,
        paymentMethodId,
      });
      const subscription = response.subscription;
      if (!subscription) {
        throw new Error("No subscription returned");
      }
      set({ subscription, loading: false });
      return subscription;
    } catch (error) {
      const message =
        error instanceof Error
          ? errorMessage(error)
          : "Failed to create subscription";
      set({ error: message, loading: false });
      throw error;
    }
  },

  updateSubscription: async (planId, interval, prorate) => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.updateSubscription({
        context: getTenantContext(),
        planId,
        interval,
        prorate,
      });
      const subscription = response.subscription;
      if (!subscription) {
        throw new Error("No subscription returned");
      }
      set({ subscription, loading: false });
      return subscription;
    } catch (error) {
      const message =
        error instanceof Error
          ? errorMessage(error)
          : "Failed to update subscription";
      set({ error: message, loading: false });
      throw error;
    }
  },

  cancelSubscription: async (cancelImmediately = false, reason) => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.cancelSubscription({
        context: getTenantContext(),
        cancelImmediately,
        reason,
      });
      set({ subscription: response.subscription ?? null, loading: false });
    } catch (error) {
      const message =
        error instanceof Error
          ? errorMessage(error)
          : "Failed to cancel subscription";
      set({ error: message, loading: false });
      throw error;
    }
  },

  resumeSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.resumeSubscription({
        context: getTenantContext(),
      });
      set({ subscription: response.subscription ?? null, loading: false });
    } catch (error) {
      const message =
        error instanceof Error
          ? errorMessage(error)
          : "Failed to reactivate subscription";
      set({ error: message, loading: false });
      throw error;
    }
  },

  setSubscription: (subscription) => {
    set({ subscription });
  },

  clearError: () => {
    set({ error: null });
  },
}));

export { BillingInterval };
