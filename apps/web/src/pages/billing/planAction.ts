import type { TierKey } from '@llamatrade/core/billing/planTiers';

export type PlanAction =
  | { kind: 'current' }
  | { kind: 'switch'; label: string }
  | { kind: 'unavailable'; label: string };

/** What a plan card's button does. Nothing above Pro is self-serve. */
export function planAction(
  tier: TierKey,
  current: TierKey | null,
  hasPlanRow: boolean
): PlanAction {
  if (tier === current) return { kind: 'current' };
  if (tier === 'enterprise') return { kind: 'unavailable', label: 'Not self-serve yet' };
  if (!hasPlanRow) return { kind: 'unavailable', label: 'Not available yet' };
  const name = tier === 'free' ? 'Free' : 'Pro';
  return { kind: 'switch', label: `Switch to ${name}` };
}
