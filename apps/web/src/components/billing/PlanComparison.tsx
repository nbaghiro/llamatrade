/**
 * PlanComparison — the three-tier comparison grid (V1). Tiers + feature rows are
 * product config (data/planTiers.ts); the CURRENT plan marker is driven by the
 * real subscription. The highlighted Pro column is an emphasis card, so it takes
 * the ORANGE offset shadow; the paper Free/Enterprise columns take the ink one.
 */

import { ArrowUpRight, Check } from 'lucide-react';

import {
  PLAN_TIERS,
  tierPricePerMonth,
  tierPriceTotal,
  type PlanTierConfig,
  type TierKey,
} from '../../data/planTiers';

import { formatUsdWhole } from './format';

interface PlanComparisonProps {
  currentTier: TierKey | null;
  yearly: boolean;
  /** Renewal date shown under the current plan's price (e.g. "Aug 14"). */
  renewDate: string;
  onChoose: (tier: PlanTierConfig) => void;
}

type CtaKind = 'current' | 'upgrade' | 'downgrade';

export default function PlanComparison({ currentTier, yearly, renewDate, onChoose }: PlanComparisonProps) {
  const currentIndex = currentTier ? PLAN_TIERS.findIndex((t) => t.key === currentTier) : -1;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {PLAN_TIERS.map((tier, i) => {
        const isPro = tier.key === 'pro';
        const isCurrent = tier.key === currentTier;

        let ctaKind: CtaKind;
        let ctaLabel: string;
        if (isCurrent) {
          ctaKind = 'current';
          ctaLabel = 'Current Plan';
        } else if (currentIndex >= 0 && i < currentIndex) {
          ctaKind = 'downgrade';
          ctaLabel = 'Downgrade';
        } else {
          ctaKind = 'upgrade';
          ctaLabel = currentTier ? 'Upgrade' : 'Choose Plan';
        }

        const ribbon = isCurrent
          ? isPro
            ? 'Your Plan · Most Popular'
            : 'Your Plan'
          : tier.badge;

        const price = tierPricePerMonth(tier, yearly);
        let note = tier.priceNote;
        if (yearly && tier.monthlyPrice > 0) {
          note = `Billed yearly · ${formatUsdWhole(tierPriceTotal(tier, true))}/yr`;
        } else if (isCurrent && renewDate !== '—') {
          note = `${tier.priceNote} · Renews ${renewDate}`;
        }

        const cardClass = isPro
          ? 'bg-orange-500 text-ink shadow-[8px_8px_0_rgb(var(--lt-orange-500))]'
          : 'bg-paper text-ink shadow-[6px_6px_0_rgb(var(--lt-ink))]';

        return (
          <div key={tier.key} className={`flex flex-col border-2 border-ink ${cardClass}`}>
            <div className="px-5 pt-5">
              <div className="mb-3 h-5">
                {ribbon && (
                  <span className="inline-block bg-ink px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-bone">
                    {ribbon}
                  </span>
                )}
              </div>
              <h3 className="font-display text-2xl uppercase leading-none tracking-tight">{tier.name}</h3>
              <p className="mt-1 font-mono text-[11px] uppercase tracking-wide text-ink/55">
                {tier.tagline}
              </p>

              <div className="mt-5 flex items-baseline gap-1">
                <span className="font-display text-4xl leading-none">{formatUsdWhole(price)}</span>
                <span className="font-mono text-[11px] uppercase tracking-wide text-ink/55">/mo</span>
              </div>
              <p className="mt-1.5 font-mono text-[10px] uppercase tracking-wide text-ink/50">{note}</p>
            </div>

            <ul className="mt-5 flex-1 px-5">
              {tier.features.map((row) => (
                <li
                  key={row.label}
                  className={`flex items-center justify-between border-t py-2.5 ${
                    isPro ? 'border-ink/15' : 'border-ink/10'
                  }`}
                >
                  <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink/55">
                    {row.label}
                  </span>
                  <span
                    className={`font-mono text-[12px] tabular-nums ${
                      row.emphasis ? 'font-bold text-green-600' : 'text-ink'
                    }`}
                  >
                    {row.value}
                  </span>
                </li>
              ))}
            </ul>

            <div className="px-5 pb-5 pt-5">
              {ctaKind === 'current' ? (
                <button
                  type="button"
                  disabled
                  className="flex w-full cursor-default items-center justify-center gap-1.5 border-2 border-ink bg-ink py-2.5 font-mono text-[11px] font-bold uppercase tracking-wide text-bone"
                >
                  <Check className="h-3.5 w-3.5" />
                  {ctaLabel}
                </button>
              ) : ctaKind === 'upgrade' ? (
                <button
                  type="button"
                  onClick={() => onChoose(tier)}
                  className="flex w-full items-center justify-center gap-1.5 border-2 border-ink bg-ink py-2.5 font-mono text-[11px] font-bold uppercase tracking-wide text-bone transition-colors hover:bg-ink/85"
                >
                  {ctaLabel}
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => onChoose(tier)}
                  className="w-full border-2 border-ink bg-bone py-2.5 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-bone"
                >
                  {ctaLabel}
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
