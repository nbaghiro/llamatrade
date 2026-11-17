import type { PlanTierConfig } from '@llamatrade/core/billing/planTiers';
import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import type { Subscription } from '@llamatrade/core/proto/billing_pb';

import { formatDate, formatUsdWhole, moneyToNumber } from '../../components/billing/format';
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

export interface PlanLine {
  name: string;
  badge: string | null;
  note: string;
  amount: string;
  ending: boolean;
}

/** The one rim-lit line at the top of Plan and usage: the plan, the deal and this month's charge. */
export function planLine(subscription: Subscription, tier: PlanTierConfig): PlanLine {
  const name = subscription.plan?.name || tier.name;
  const listed = moneyToNumber(subscription.plan?.monthlyPrice) || tier.monthlyPrice;
  if (subscription.cancelAtPeriodEnd) {
    return {
      name,
      badge: 'Ending',
      note: `Ends ${formatDate(subscription.currentPeriodEnd)}. No further charges.`,
      amount: formatUsdWhole(0),
      ending: true,
    };
  }
  if (subscription.isTrial) {
    return {
      name,
      badge: 'Trial',
      note: `Trial ends ${formatDate(subscription.trialEnd)}. Then ${formatUsdWhole(listed)} a month.`,
      amount: formatUsdWhole(0),
      ending: false,
    };
  }
  const amount = moneyToNumber(subscription.currentPrice) || listed;
  if (amount <= 0) {
    return {
      name,
      badge: null,
      note: 'No charge. Compare plans to raise your limits.',
      amount: formatUsdWhole(0),
      ending: false,
    };
  }
  return {
    name,
    badge: null,
    note: `Billed monthly. Next invoice ${formatDate(subscription.currentPeriodEnd)}.`,
    amount: formatUsdWhole(amount),
    ending: false,
  };
}
