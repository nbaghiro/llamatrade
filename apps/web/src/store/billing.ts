/**
 * Billing state management with Zustand
 */

import { create } from 'zustand';

import { billingApi } from '../services/billing';
import type {
  BillingCycle,
  Invoice,
  PaymentMethod,
  Plan,
  Subscription,
} from '../types/billing';

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
  createSubscription: (planId: string, paymentMethodId: string, billingCycle: BillingCycle) => Promise<Subscription>;
  updateSubscription: (planId: string) => Promise<Subscription>;
  cancelSubscription: (atPeriodEnd?: boolean) => Promise<void>;
  reactivateSubscription: () => Promise<void>;
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
      const response = await billingApi.getPlans();
      set({ plans: response.data, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch plans';
      set({ error: message, loading: false });
    }
  },

  fetchSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.getSubscription();
      set({ subscription: response.data, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch subscription';
      set({ error: message, loading: false });
    }
  },

  fetchPaymentMethods: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.getPaymentMethods();
      set({ paymentMethods: response.data, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch payment methods';
      set({ error: message, loading: false });
    }
  },

  fetchInvoices: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.getInvoices();
      set({ invoices: response.data, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch invoices';
      set({ error: message, loading: false });
    }
  },

  createSubscription: async (planId, paymentMethodId, billingCycle) => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.createSubscription({
        plan_id: planId,
        payment_method_id: paymentMethodId,
        billing_cycle: billingCycle,
      });
      set({ subscription: response.data, loading: false });
      return response.data;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create subscription';
      set({ error: message, loading: false });
      throw error;
    }
  },

  updateSubscription: async (planId) => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.updateSubscription({ plan_id: planId });
      set({ subscription: response.data, loading: false });
      return response.data;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update subscription';
      set({ error: message, loading: false });
      throw error;
    }
  },

  cancelSubscription: async (atPeriodEnd = true) => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.cancelSubscription({ at_period_end: atPeriodEnd });
      set({ subscription: response.data, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to cancel subscription';
      set({ error: message, loading: false });
      throw error;
    }
  },

  reactivateSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const response = await billingApi.reactivateSubscription();
      set({ subscription: response.data, loading: false });
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
