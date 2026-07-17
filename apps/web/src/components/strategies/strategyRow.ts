/**
 * Strategies table/detail view-model. The derivations are shared (core), so this
 * file is the web surface: it re-exports them plus the swatch palette, and owns
 * the Tailwind pill class map (the one web-only bit).
 */

import type { StrategyPill } from '@llamatrade/core/strategy/row';

// Categorical swatch palette (Monolith tokens), assigned by table slot.
export { strategyColors as STRATEGY_COLORS } from '@llamatrade/core/theme';
export * from '@llamatrade/core/strategy/row';

const PILL_CLASS: Record<StrategyPill, string> = {
  LIVE: 'bg-green-500 text-bone',
  PAPER: 'bg-orange-500 text-ink',
  PAUSED: 'bg-ink text-bone',
  DRAFT: 'bg-bone text-ink',
  ARCHIVED: 'bg-gray-200 text-ink/60',
};

export function pillClass(pill: StrategyPill): string {
  return PILL_CLASS[pill];
}
