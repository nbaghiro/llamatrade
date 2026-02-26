/**
 * Billing API service
 */

import type {
  AttachPaymentMethodRequest,
  CancelSubscriptionRequest,
  CreateSubscriptionRequest,
  Invoice,
  PaymentMethod,
  Plan,
  SetupIntentResponse,
  Subscription,
  UpdateSubscriptionRequest,
} from '../types/billing';

import { api } from './api';

export const billingApi = {
  // Plans - Kong routes /api/subscriptions to billing service
  getPlans: () => api.get<Plan[]>('/subscriptions/plans'),

  getPlan: (planId: string) => api.get<Plan>(`/subscriptions/plans/${planId}`),

  // Subscription
  getSubscription: () => api.get<Subscription | null>('/subscriptions/current'),

  createSubscription: (data: CreateSubscriptionRequest) =>
    api.post<Subscription>('/subscriptions', data),

  updateSubscription: (data: UpdateSubscriptionRequest) =>
    api.put<Subscription>('/subscriptions', data),

  cancelSubscription: (data: CancelSubscriptionRequest = { at_period_end: true }) =>
    api.post<Subscription>('/subscriptions/cancel', data),

  reactivateSubscription: () => api.post<Subscription>('/subscriptions/reactivate'),

  // Payment methods - Kong routes /api/billing to billing service
  createSetupIntent: () => api.post<SetupIntentResponse>('/billing/payment-methods/setup-intent'),

  getPaymentMethods: () => api.get<PaymentMethod[]>('/billing/payment-methods'),

  attachPaymentMethod: (data: AttachPaymentMethodRequest) =>
    api.post<PaymentMethod>('/billing/payment-methods', data),

  deletePaymentMethod: (id: string) => api.delete(`/billing/payment-methods/${id}`),

  setDefaultPaymentMethod: (id: string) =>
    api.put<PaymentMethod>(`/billing/payment-methods/${id}/default`),

  // Invoices
  getInvoices: () => api.get<Invoice[]>('/subscriptions/invoices'),
};

export default billingApi;
