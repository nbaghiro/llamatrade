import type { TierKey } from '@llamatrade/core/billing/planTiers';

const TIER_RANK: Record<TierKey, number> = { free: 0, pro: 1, enterprise: 2 };

export type PlanAction =
  | { kind: 'current' }
  | { kind: 'switch'; label: string }
  | { kind: 'unavailable'; label: string };

/**
 * What a plan card's button does. In the closed beta only a move down to Free is allowed,
 * since it never charges; nothing above Pro is self-serve.
 */
export function planAction(
  tier: TierKey,
  current: TierKey | null,
  beta: boolean,
  hasPlanRow: boolean
): PlanAction {
  if (tier === current) return { kind: 'current' };
  if (tier === 'enterprise') {
    return {
      kind: 'unavailable',
      label: beta ? 'Not available in the beta' : 'Not self-serve yet',
    };
  }
  if (!hasPlanRow) return { kind: 'unavailable', label: 'Not available yet' };
  const moveUp = current === null || TIER_RANK[tier] > TIER_RANK[current];
  if (beta && moveUp) return { kind: 'unavailable', label: 'Opens after the beta' };
  const name = tier === 'free' ? 'Free' : 'Pro';
  return { kind: 'switch', label: `Switch to ${name}` };
}
