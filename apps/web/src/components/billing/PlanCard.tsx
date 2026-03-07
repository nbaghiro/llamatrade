/**
 * PlanCard component - displays plan details with pricing
 */

import { Check } from 'lucide-react';

import type { Plan } from '../../generated/proto/billing_pb';
import { PlanTier } from '../../generated/proto/billing_pb';
import type { Money } from '../../generated/proto/common_pb';

type BillingCycle = 'monthly' | 'yearly';

interface PlanCardProps {
  plan: Plan;
  billingCycle: BillingCycle;
  isCurrentPlan: boolean;
  onSelect: (plan: Plan) => void;
}

// Helper to get numeric price from Money type
function getPrice(money: Money | undefined): number {
  if (!money) return 0;
  return parseFloat(money.amount) || 0;
}

export default function PlanCard({
  plan,
  billingCycle,
  isCurrentPlan,
  onSelect,
}: PlanCardProps) {
  const monthlyPrice = getPrice(plan.monthlyPrice);
  const yearlyPrice = getPrice(plan.yearlyPrice);

  const price = billingCycle === 'monthly' ? monthlyPrice : yearlyPrice;
  const monthlyEquivalent = billingCycle === 'yearly' ? Math.round(yearlyPrice / 12) : monthlyPrice;
  const savings = billingCycle === 'yearly' ? monthlyPrice * 12 - yearlyPrice : 0;

  const isPro = plan.tier === PlanTier.PRO;
  const isFree = plan.tier === PlanTier.FREE;

  // Build features list from plan limits
  const features: string[] = [];

  if (plan.maxBacktestsPerMonth > 0) {
    features.push(`${plan.maxBacktestsPerMonth} backtests/month`);
  } else if (plan.maxBacktestsPerMonth === -1 || plan.maxBacktestsPerMonth === 0) {
    features.push('Unlimited backtests');
  }

  if (plan.maxStrategies > 0) {
    features.push(`${plan.maxStrategies} ${plan.maxStrategies === 1 ? 'strategy' : 'strategies'}`);
  }

  if (plan.maxLiveSessions > 0) {
    features.push(`${plan.maxLiveSessions} live ${plan.maxLiveSessions === 1 ? 'session' : 'sessions'}`);
  }

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

      {plan.description && (
        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          {plan.description}
        </p>
      )}

      <ul className="mb-6 flex-1 space-y-3">
        {features.map((feature) => (
          <li key={feature} className="flex items-center gap-2">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {feature}
            </span>
          </li>
        ))}
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
