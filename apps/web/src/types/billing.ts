/**
 * Billing and subscription types
 */

export type PlanTier = 'free' | 'starter' | 'pro';

export type SubscriptionStatus = 'active' | 'past_due' | 'cancelled' | 'trialing' | 'paused';

export type BillingCycle = 'monthly' | 'yearly';

export interface PlanFeatures {
  backtests: boolean;
  paper_trading: boolean;
  live_trading: boolean;
  basic_indicators: boolean;
  all_indicators: boolean;
  email_alerts: boolean;
  sms_alerts: boolean;
  webhook_alerts: boolean;
  priority_support: boolean;
}

export interface PlanLimits {
  backtests_per_month: number | null;
  live_strategies: number | null;
  api_calls_per_day: number | null;
}

export interface Plan {
  id: string;
  name: string;
  tier: PlanTier;
  price_monthly: number;
  price_yearly: number;
  features: Record<string, boolean>;
  limits: Record<string, number | null>;
  trial_days: number;
}

export interface Subscription {
  id: string;
  tenant_id: string;
  plan: Plan;
  status: SubscriptionStatus;
  billing_cycle: BillingCycle;
  current_period_start: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
  trial_start: string | null;
  trial_end: string | null;
  stripe_subscription_id: string | null;
  created_at: string;
}

export interface PaymentMethod {
  id: string;
  type: string;
  card_brand: string | null;
  card_last4: string | null;
  card_exp_month: number | null;
  card_exp_year: number | null;
  is_default: boolean;
}

export interface SetupIntentResponse {
  client_secret: string;
  customer_id: string;
}

export interface Invoice {
  id: string;
  amount: number;
  currency: string;
  status: string;
  period_start: string;
  period_end: string;
  paid_at: string | null;
  invoice_pdf: string | null;
  hosted_invoice_url: string | null;
}

// Request types
export interface CreateSubscriptionRequest {
  plan_id: string;
  payment_method_id: string;
  billing_cycle: BillingCycle;
}

export interface UpdateSubscriptionRequest {
  plan_id: string;
}

export interface CancelSubscriptionRequest {
  at_period_end: boolean;
}

export interface AttachPaymentMethodRequest {
  payment_method_id: string;
}
