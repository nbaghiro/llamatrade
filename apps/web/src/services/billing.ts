/**
 * Billing gRPC service
 *
 * This module wraps the billingClient with convenience functions.
 * It uses the proto-generated types directly.
 */

import { BillingInterval } from '../generated/proto/billing_pb';

import { billingClient } from './grpc-client';

export const billingApi = {
  // Plans
  getPlans: () => billingClient.listPlans({}),

  // Subscription
  getSubscription: () => billingClient.getSubscription({}),

  createSubscription: (planId: string, interval: BillingInterval, paymentMethodId?: string, promoCode?: string) =>
    billingClient.createSubscription({ planId, interval, paymentMethodId, promoCode }),

  updateSubscription: (planId: string, interval?: BillingInterval, prorate?: boolean) =>
    billingClient.updateSubscription({ planId, interval, prorate }),

  cancelSubscription: (cancelImmediately: boolean = false, reason?: string) =>
    billingClient.cancelSubscription({ cancelImmediately, reason }),

  resumeSubscription: () => billingClient.resumeSubscription({}),

  // Payment methods
  getPaymentMethods: () => billingClient.listPaymentMethods({}),

  addPaymentMethod: (setupIntentId: string, setAsDefault?: boolean) =>
    billingClient.addPaymentMethod({ setupIntentId, setAsDefault }),

  removePaymentMethod: (paymentMethodId: string) =>
    billingClient.removePaymentMethod({ paymentMethodId }),

  // Invoices
  getInvoices: () => billingClient.listInvoices({}),

  getInvoice: (invoiceId: string) => billingClient.getInvoice({ invoiceId }),

  // Usage
  getUsage: (periodId?: string) => billingClient.getUsage({ periodId }),

  // Stripe integration
  createCheckoutSession: (planId: string, interval: BillingInterval, successUrl: string, cancelUrl: string) =>
    billingClient.createCheckoutSession({ planId, interval, successUrl, cancelUrl }),

  createPortalSession: (returnUrl: string) =>
    billingClient.createPortalSession({ returnUrl }),
};

export default billingApi;
