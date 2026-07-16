/**
 * Plan tiers + feature rows — PRODUCT config, not per-tenant data.
 *
 * The billing seed only carries Free + Pro; Enterprise is a sales/upgrade tier
 * with no self-serve plan row. The comparison grid and the usage-meter limits
 * are driven entirely by this typed constant, while the *current* plan and all
 * usage figures come from the real billing/strategy/backtest/portfolio APIs.
 */

import { PlanTier, type Subscription } from '../generated/proto/billing_pb';

export type TierKey = 'free' | 'pro' | 'enterprise';

/** Yearly billing discount reflected by the MONTHLY/YEARLY toggle (-17%). */
export const YEARLY_DISCOUNT = 0.17;

export interface PlanFeatureRow {
  label: string;
  value: string;
  /** Renders the value in the "up/positive" green (used for Enterprise's "Unlimited"). */
  emphasis?: boolean;
}

/** Numeric usage limits per period; -1 means unlimited. */
export interface PlanLimits {
  strategies: number;
  backtestsPerMonth: number;
  liveSessions: number;
  copilotMessages: number;
}

export interface PlanTierConfig {
  key: TierKey;
  name: string;
  tagline: string;
  monthlyPrice: number;
  /** Sub-price caption (e.g. "Free forever", "Billed monthly"). */
  priceNote: string;
  /** Ribbon label shown above the column ("MOST POPULAR" / "SCALE"). */
  badge?: string;
  features: PlanFeatureRow[];
  limits: PlanLimits;
}

/** Ordered low -> high; index drives Upgrade vs Downgrade labelling. */
export const PLAN_TIERS: PlanTierConfig[] = [
  {
    key: 'free',
    name: 'Free',
    tagline: 'Paper trading & exploration',
    monthlyPrice: 0,
    priceNote: 'Free forever',
    features: [
      { label: 'Strategies', value: '1' },
      { label: 'Live Trading', value: 'Paper only' },
      { label: 'Backtests / mo', value: '10' },
      { label: 'Copilot', value: 'Basic' },
      { label: 'Support', value: 'Community' },
    ],
    limits: { strategies: 1, backtestsPerMonth: 10, liveSessions: 0, copilotMessages: 100 },
  },
  {
    key: 'pro',
    name: 'Pro',
    tagline: 'For active retail algo traders',
    monthlyPrice: 49,
    priceNote: 'Billed monthly',
    badge: 'Most Popular',
    features: [
      { label: 'Strategies', value: '10' },
      { label: 'Live Trading', value: '3 live sessions' },
      { label: 'Backtests / mo', value: '500' },
      { label: 'Copilot', value: 'Full · DSL gen' },
      { label: 'Support', value: 'Priority email' },
    ],
    limits: { strategies: 10, backtestsPerMonth: 500, liveSessions: 3, copilotMessages: 2000 },
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    tagline: 'Desks, funds & power users',
    monthlyPrice: 199,
    priceNote: 'Volume & annual discounts',
    badge: 'Scale',
    features: [
      { label: 'Strategies', value: 'Unlimited', emphasis: true },
      { label: 'Live Trading', value: 'Unlimited', emphasis: true },
      { label: 'Backtests / mo', value: 'Unlimited', emphasis: true },
      { label: 'Copilot', value: 'Full + fine-tune', emphasis: true },
      { label: 'Support', value: 'Dedicated + SLA', emphasis: true },
    ],
    limits: { strategies: -1, backtestsPerMonth: -1, liveSessions: -1, copilotMessages: -1 },
  },
];

export const PLAN_TIER_BY_KEY: Record<TierKey, PlanTierConfig> = Object.fromEntries(
  PLAN_TIERS.map((t) => [t.key, t]),
) as Record<TierKey, PlanTierConfig>;

/**
 * Resolve which config tier the real subscription maps to. Prefers the proto
 * PlanTier enum, then falls back to the plan name — so a live subscription
 * always drives the "current plan" marker rather than a hardcoded guess.
 */
export function resolveCurrentTier(subscription: Subscription | null): TierKey | null {
  if (!subscription) return null;
  switch (subscription.plan?.tier) {
    case PlanTier.PRO:
      return 'pro';
    case PlanTier.STARTER:
      return 'pro';
    case PlanTier.FREE:
      return 'free';
  }
  const name = subscription.plan?.name?.toLowerCase() ?? '';
  if (name.includes('enterprise')) return 'enterprise';
  if (name.includes('pro') || name.includes('starter')) return 'pro';
  if (name.includes('free')) return 'free';
  return null;
}

/** Per-month price for the selected billing cycle (yearly applies the discount). */
export function tierPricePerMonth(tier: PlanTierConfig, yearly: boolean): number {
  if (tier.monthlyPrice === 0) return 0;
  return yearly ? Math.round(tier.monthlyPrice * (1 - YEARLY_DISCOUNT)) : tier.monthlyPrice;
}

/** Total charged up-front for the selected cycle. */
export function tierPriceTotal(tier: PlanTierConfig, yearly: boolean): number {
  if (tier.monthlyPrice === 0) return 0;
  return yearly ? Math.round(tier.monthlyPrice * 12 * (1 - YEARLY_DISCOUNT)) : tier.monthlyPrice;
}
