import type { PlanTierConfig } from '@llamatrade/core/billing/planTiers';
import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import type { PaymentMethod, Subscription } from '@llamatrade/core/proto/billing_pb';

import {
  cardSummary,
  formatDate,
  formatUsd,
  formatUsdWhole,
  moneyToNumber,
} from '../../components/billing/format';
import type { AuthUser } from '../../store/auth';

export function displayName(user: Pick<AuthUser, 'firstName' | 'lastName'> | null): string {
  return [user?.firstName, user?.lastName]
    .map((p) => p?.trim())
    .filter(Boolean)
    .join(' ');
}

/** The credential to show first: an active one if any, else the newest. */
export function primaryCredential(
  list: readonly AlpacaCredentialsListItem[]
): AlpacaCredentialsListItem | null {
  return list.find((c) => c.isActive) ?? list[0] ?? null;
}

export function maskedKey(prefix: string): string {
  return `${prefix}••••`;
}

/** Why a pasted key can't be checked as the one in use, or null when it can. */
export function keyMismatch(pasted: string, prefix: string): string | null {
  const key = pasted.trim();
  if (!key) return 'Enter the key ID.';
  if (prefix && !key.startsWith(prefix)) {
    return `That key doesn't match the one in use (${maskedKey(prefix)}).`;
  }
  return null;
}

export interface PlanCell {
  label: string;
  value: string;
  sub: string;
}

/** The three figures under the plan name: next invoice, amount and how it's paid. */
export function planCells(
  subscription: Subscription,
  tier: PlanTierConfig,
  card: PaymentMethod | null,
  beta: boolean
): PlanCell[] {
  const listed = moneyToNumber(subscription.plan?.monthlyPrice) || tier.monthlyPrice;
  const paidWith: PlanCell = card
    ? {
        label: 'Paid with',
        value: card.cardLast4 ? `•••• ${card.cardLast4}` : cardSummary(card.cardBrand, ''),
        sub: `${cardSummary(card.cardBrand, '')}, ${card.isDefault ? 'default card' : 'saved card'}`,
      }
    : {
        label: 'Paid with',
        value: 'No card',
        sub: beta ? 'not needed yet' : 'add one to keep the plan',
      };
  if (beta) {
    return [
      { label: 'Next invoice', value: 'None', sub: 'during the beta' },
      { label: 'Amount', value: formatUsd(0), sub: `listed at ${formatUsdWhole(listed)} a month` },
      paidWith,
    ];
  }
  const amount = moneyToNumber(subscription.currentPrice) || listed;
  const ends = subscription.cancelAtPeriodEnd;
  return [
    {
      label: ends ? 'Plan ends' : 'Next invoice',
      value: formatDate(subscription.currentPeriodEnd),
      sub: ends ? 'no further charges' : 'billed monthly',
    },
    { label: 'Amount', value: formatUsd(ends ? 0 : amount), sub: 'a month' },
    paidWith,
  ];
}
