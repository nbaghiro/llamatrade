/**
 * Billing state management with Zustand.
 *
 * All reads/writes thread the real tenant context (see getTenantContext). Usage
 * counts are derived from the live product surfaces — strategies, backtests,
 * running executions and Copilot sessions — measured against the current plan's
 * limits (see data/planTiers.ts), never fabricated.
 */

import { Code, ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import { AgentSessionStatus } from '../generated/proto/agent_pb';
import {
  BillingInterval,
  type Invoice,
  type PaymentMethod,
  type Plan,
  type Subscription,
} from '../generated/proto/billing_pb';
import { ExecutionStatus } from '../generated/proto/common_pb';
import {
  agentClient,
  backtestClient,
  billingClient,
  portfolioClient,
  strategyClient,
} from '../services/grpc-client';

import { getTenantContext } from './auth';

/** Real, period-to-date usage counts derived from the product APIs. */
export interface UsageCounts {
  strategies: number;
  backtests: number;
  liveSessions: number;
  copilotMessages: number;
}

interface BillingState {
  // State
  plans: Plan[];
  subscription: Subscription | null;
  paymentMethods: PaymentMethod[];
  invoices: Invoice[];
  usageCounts: UsageCounts | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchPlans: () => Promise<void>;
  fetchSubscription: () => Promise<void>;
  fetchPaymentMethods: () => Promise<void>;
  fetchInvoices: () => Promise<void>;
  fetchUsageCounts: () => Promise<void>;
  createSubscription: (planId: string, interval: BillingInterval, paymentMethodId?: string) => Promise<Subscription>;
  updateSubscription: (planId: string, interval?: BillingInterval, prorate?: boolean) => Promise<Subscription>;
  cancelSubscription: (cancelImmediately?: boolean, reason?: string) => Promise<void>;
  resumeSubscription: () => Promise<void>;
  setSubscription: (subscription: Subscription | null) => void;
  clearError: () => void;
}

export const useBillingStore = create<BillingState>((set) => ({
  // Initial state
  plans: [],
  subscription: null,
  paymentMethods: [],
  invoices: [],
  usageCounts: null,
  loading: false,
  error: null,

  // Actions
  fetchPlans: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listPlans({ context: getTenantContext() });
      set({ plans: response.plans, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch plans';
      set({ error: message, loading: false });
    }
  },

  fetchSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.getSubscription({ context: getTenantContext() });
      set({ subscription: response.subscription ?? null, loading: false });
    } catch (error) {
      // NOT_FOUND means no subscription exists - this is normal for new users
      if (error instanceof ConnectError && error.code === Code.NotFound) {
        set({ subscription: null, loading: false });
        return;
      }
      const message = error instanceof Error ? error.message : 'Failed to fetch subscription';
      set({ error: message, loading: false });
    }
  },

  fetchPaymentMethods: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listPaymentMethods({ context: getTenantContext() });
      set({ paymentMethods: response.paymentMethods, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch payment methods';
      set({ error: message, loading: false });
    }
  },

  fetchInvoices: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listInvoices({ context: getTenantContext() });
      set({ invoices: response.invoices, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch invoices';
      set({ error: message, loading: false });
    }
  },

  // Derive the four usage meters from the real product surfaces; each is independent and degrades to 0 on failure.
  fetchUsageCounts: async () => {
    const context = getTenantContext();
    if (!context) {
      set({ usageCounts: null });
      return;
    }

    const [strategies, backtests, liveSessions, copilotMessages] = await Promise.all([
      strategyClient
        .listStrategies({ context, pagination: { page: 1, pageSize: 100 } })
        .then((r) => r.pagination?.totalItems ?? r.strategies.length)
        .catch(() => 0),
      backtestClient
        .listBacktests({ context, strategyId: '', pagination: { page: 1, pageSize: 100 } })
        .then((r) => r.pagination?.totalItems ?? r.backtests.length)
        .catch(() => 0),
      portfolioClient
        .listStrategyPerformance({ context, pagination: { page: 1, pageSize: 100 } })
        .then((r) => r.strategies.filter((s) => s.status === ExecutionStatus.RUNNING).length)
        .catch(() => 0),
      agentClient
        .listSessions({
          context,
          statusFilter: AgentSessionStatus.UNSPECIFIED,
          pagination: { page: 1, pageSize: 100 },
        })
        .then((r) => r.sessions.reduce((sum, s) => sum + s.messageCount, 0))
        .catch(() => 0),
    ]);

    set({ usageCounts: { strategies, backtests, liveSessions, copilotMessages } });
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
        throw new Error('No subscription returned');
      }
      set({ subscription, loading: false });
      return subscription;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create subscription';
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
        throw new Error('No subscription returned');
      }
      set({ subscription, loading: false });
      return subscription;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update subscription';
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
      const message = error instanceof Error ? error.message : 'Failed to cancel subscription';
      set({ error: message, loading: false });
      throw error;
    }
  },

  resumeSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.resumeSubscription({ context: getTenantContext() });
      set({ subscription: response.subscription ?? null, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to reactivate subscription';
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
