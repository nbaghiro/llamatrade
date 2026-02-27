/**
 * Billing state management with Zustand
 */

import { Code, ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import {
  BillingInterval,
  type Invoice,
  type PaymentMethod,
  type Plan,
  type Subscription,
} from '../generated/proto/llamatrade/v1/billing_pb';
import { billingClient } from '../services/grpc-client';

interface BillingState {
  // State
  plans: Plan[];
  subscription: Subscription | null;
  paymentMethods: PaymentMethod[];
  invoices: Invoice[];
  loading: boolean;
  error: string | null;

  // Actions
  fetchPlans: () => Promise<void>;
  fetchSubscription: () => Promise<void>;
  fetchPaymentMethods: () => Promise<void>;
  fetchInvoices: () => Promise<void>;
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
  loading: false,
  error: null,

  // Actions
  fetchPlans: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listPlans({});
      set({ plans: response.plans, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch plans';
      set({ error: message, loading: false });
    }
  },

  fetchSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.getSubscription({});
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
      const response = await billingClient.listPaymentMethods({});
      set({ paymentMethods: response.paymentMethods, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch payment methods';
      set({ error: message, loading: false });
    }
  },

  fetchInvoices: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.listInvoices({});
      set({ invoices: response.invoices, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch invoices';
      set({ error: message, loading: false });
    }
  },

  createSubscription: async (planId, interval, paymentMethodId) => {
    set({ loading: true, error: null });
    try {
      const response = await billingClient.createSubscription({
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
      const response = await billingClient.updateSubscription({ planId, interval, prorate });
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
      const response = await billingClient.cancelSubscription({ cancelImmediately, reason });
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
      const response = await billingClient.resumeSubscription({});
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

// Re-export for convenience
export { BillingInterval };
