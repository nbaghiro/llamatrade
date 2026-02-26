/**
 * PlanCard component - displays plan details with pricing
 */

import { Check } from 'lucide-react';

import type { BillingCycle, Plan } from '../../types/billing';

interface PlanCardProps {
  plan: Plan;
  billingCycle: BillingCycle;
  isCurrentPlan: boolean;
  onSelect: (plan: Plan) => void;
}

const FEATURE_LABELS: Record<string, string> = {
  backtests: 'Backtesting',
  paper_trading: 'Paper Trading',
  live_trading: 'Live Trading',
  basic_indicators: 'Basic Indicators',
  all_indicators: 'All Indicators',
  email_alerts: 'Email Alerts',
  sms_alerts: 'SMS Alerts',
  webhook_alerts: 'Webhook Alerts',
  priority_support: 'Priority Support',
};

export default function PlanCard({
  plan,
  billingCycle,
  isCurrentPlan,
  onSelect,
}: PlanCardProps) {
  const price = billingCycle === 'monthly' ? plan.price_monthly : plan.price_yearly;
  const monthlyEquivalent =
    billingCycle === 'yearly' ? Math.round(plan.price_yearly / 12) : plan.price_monthly;
  const savings =
    billingCycle === 'yearly' ? plan.price_monthly * 12 - plan.price_yearly : 0;

  const enabledFeatures = Object.entries(plan.features)
    .filter(([_, enabled]) => enabled)
    .map(([key]) => key);

  const isPro = plan.tier === 'pro';
  const isFree = plan.tier === 'free';

  return (
    <div
      className={`relative flex flex-col rounded-2xl border p-6 ${
        isPro
          ? 'border-indigo-500 bg-indigo-50/50 dark:border-indigo-400 dark:bg-indigo-950/20'
          : 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900'
      } ${isCurrentPlan ? 'ring-2 ring-indigo-500' : ''}`}
    >
      {isPro && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="rounded-full bg-indigo-600 px-3 py-1 text-xs font-medium text-white">
            Most Popular
          </span>
        </div>
      )}

      {isCurrentPlan && (
        <div className="absolute -top-3 right-4">
          <span className="rounded-full bg-green-600 px-3 py-1 text-xs font-medium text-white">
            Current Plan
          </span>
        </div>
      )}

      <div className="mb-4">
        <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{plan.name}</h3>
        {plan.trial_days > 0 && (
          <span className="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            {plan.trial_days}-day free trial
          </span>
        )}
      </div>

      <div className="mb-6">
        <div className="flex items-baseline">
          <span className="text-4xl font-bold text-gray-900 dark:text-gray-100">
            ${isFree ? '0' : monthlyEquivalent}
          </span>
          {!isFree && (
            <span className="ml-1 text-gray-500 dark:text-gray-400">/month</span>
          )}
        </div>
        {billingCycle === 'yearly' && !isFree && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            ${price}/year{' '}
            {savings > 0 && (
              <span className="text-green-600 dark:text-green-400">
                (Save ${savings})
              </span>
            )}
          </p>
        )}
      </div>

      <ul className="mb-6 flex-1 space-y-3">
        {enabledFeatures.map((feature) => (
          <li key={feature} className="flex items-center gap-2">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {FEATURE_LABELS[feature] || feature}
            </span>
          </li>
        ))}
        {plan.limits.backtests_per_month !== null && (
          <li className="flex items-center gap-2">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {plan.limits.backtests_per_month} backtests/month
            </span>
          </li>
        )}
        {plan.limits.backtests_per_month === null && (
          <li className="flex items-center gap-2">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              Unlimited backtests
            </span>
          </li>
        )}
        {plan.limits.live_strategies !== null && plan.limits.live_strategies > 0 && (
          <li className="flex items-center gap-2">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {plan.limits.live_strategies} live{' '}
              {plan.limits.live_strategies === 1 ? 'strategy' : 'strategies'}
            </span>
          </li>
        )}
      </ul>

      <button
        onClick={() => onSelect(plan)}
        disabled={isCurrentPlan}
        className={`w-full rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
          isCurrentPlan
            ? 'cursor-not-allowed bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500'
            : isPro
              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
              : 'bg-gray-900 text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200'
        }`}
      >
        {isCurrentPlan ? 'Current Plan' : isFree ? 'Downgrade' : 'Subscribe'}
      </button>
    </div>
  );
}
