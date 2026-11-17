import {
  PLAN_TIERS,
  resolveCurrentTier,
  tierPricePerMonth,
  type PlanTierConfig,
  type TierKey,
} from '@llamatrade/core/billing/planTiers';
import { errorMessage } from '@llamatrade/core/errors';
import { BillingInterval, PlanTier, type Plan } from '@llamatrade/core/proto/billing_pb';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { ChevronLeft } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatUsdWhole } from '../../components/billing/format';
import { Dialog, Segmented, Skeleton } from '../../components/ui';
import { asSentence } from '../../lib/format';
import { KV, Panel } from '../settings/parts';

import { planAction } from './planAction';

type Cycle = 'monthly' | 'yearly';

function planRowFor(plans: readonly Plan[], tier: TierKey): Plan | undefined {
  const wanted = tier === 'free' ? PlanTier.FREE : PlanTier.PRO;
  return (
    plans.find((p) => p.tier === wanted) ?? plans.find((p) => p.name.toLowerCase().includes(tier))
  );
}

export default function PlansPage() {
  const plans = useBillingStore((s) => s.plans);
  const subscription = useBillingStore((s) => s.subscription);
  const paymentMethods = useBillingStore((s) => s.paymentMethods);
  const subscriptionLoaded = useBillingStore((s) => s.loaded.subscription ?? false);
  const fetchPlans = useBillingStore((s) => s.fetchPlans);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const fetchPaymentMethods = useBillingStore((s) => s.fetchPaymentMethods);
  const createSubscription = useBillingStore((s) => s.createSubscription);
  const updateSubscription = useBillingStore((s) => s.updateSubscription);
  const [cycle, setCycle] = useState<Cycle>('monthly');
  const [pending, setPending] = useState<{ tier: PlanTierConfig; plan: Plan } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPlans().catch(() => undefined);
    fetchSubscription().catch(() => undefined);
    fetchPaymentMethods().catch(() => undefined);
  }, [fetchPlans, fetchSubscription, fetchPaymentMethods]);

  const current = resolveCurrentTier(subscription);
  const yearly = cycle === 'yearly';
  const interval = yearly ? BillingInterval.YEARLY : BillingInterval.MONTHLY;

  const confirmSwitch = async () => {
    if (!pending) return;
    setSaving(true);
    setError(null);
    try {
      if (subscription) await updateSubscription(pending.plan.id, interval);
      else {
        const card = paymentMethods.find((p) => p.isDefault) ?? paymentMethods[0];
        await createSubscription(pending.plan.id, interval, card?.id);
      }
      setPending(null);
    } catch (e) {
      setError(
        e instanceof Error
          ? asSentence(errorMessage(e)) || null
          : "The plan couldn't be changed. Please try again."
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <Link
        to="/settings/plan"
        className="mb-2 inline-flex items-center gap-0.5 text-[13px] text-accent hover:underline"
      >
        <ChevronLeft className="h-4 w-4" />
        Plan and usage
      </Link>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 text-[21px] leading-tight">Plans</h1>
          <div className="mt-[3px] text-[12.5px] text-fg-3">Prices in USD</div>
        </div>
        <Segmented
          label="Billing period"
          value={cycle}
          onChange={setCycle}
          options={[
            { key: 'monthly', label: 'Monthly' },
            { key: 'yearly', label: 'Yearly, save 17%' },
          ]}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {PLAN_TIERS.map((tier) => {
          const plan = planRowFor(plans, tier.key);
          const action = subscriptionLoaded
            ? planAction(tier.key, current, plan !== undefined)
            : null;
          const isCurrent = action?.kind === 'current';
          return (
            <Panel
              key={tier.key}
              current={isCurrent}
              title={tier.name}
              aside={isCurrent ? <span className="badge badge-accent">Your plan</span> : undefined}
            >
              <div className="grid gap-3 px-3.5 py-3">
                <div>
                  <span className="num text-[30px] leading-none text-fg">
                    {formatUsdWhole(tierPricePerMonth(tier, yearly))}
                  </span>
                  <span className="text-fg-3">
                    {' '}
                    a month{yearly && tier.monthlyPrice > 0 ? ', billed yearly' : ''}
                  </span>
                  <div className="mt-1 text-[12.5px] text-fg-2">{tier.tagline}</div>
                </div>
                <div>
                  {tier.features.map((f) => (
                    <KV key={f.label} label={f.label}>
                      {f.value}
                    </KV>
                  ))}
                </div>
                {action === null ? (
                  <Skeleton className="h-8 w-full" />
                ) : action.kind === 'switch' && plan ? (
                  <button
                    type="button"
                    className="btn btn-secondary w-full"
                    onClick={() => {
                      setError(null);
                      setPending({ tier, plan });
                    }}
                  >
                    {action.label}
                  </button>
                ) : (
                  <button type="button" className="btn btn-secondary w-full" disabled>
                    {action.kind === 'current' ? 'Current plan' : action.label}
                  </button>
                )}
              </div>
            </Panel>
          );
        })}
      </div>

      <Dialog
        open={pending !== null}
        onClose={() => setPending(null)}
        title={`Switch to ${pending?.tier.name ?? ''}?`}
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setPending(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={() => {
                confirmSwitch().catch(() => undefined);
              }}
            >
              {saving ? 'Switching…' : `Switch to ${pending?.tier.name ?? ''}`}
            </button>
          </>
        }
      >
        <p className="m-0 text-[13px] text-fg-2">
          {pending?.tier.key === 'free'
            ? 'Free allows one strategy, ten backtests a month and paper trading. It has no charge.'
            : `You'll be on ${pending?.tier.name ?? ''} from today.`}
        </p>
        {error && <p className="m-0 text-xs text-risk">{error}</p>}
      </Dialog>
    </div>
  );
}
