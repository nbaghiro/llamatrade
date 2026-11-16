import { TemplateCategory, type StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';

import { ALL_CATEGORIES } from '../../data/strategy-templates';
import { writtenScenarios, type WrittenHolding } from '../../lib/outline';

/** Starter templates for a new account, by name, in this order. */
export const STARTER_TEMPLATES = [
  'Classic 60/40',
  'All-Weather Portfolio',
  'Dual Momentum',
] as const;

/** Templates shown first in the new-strategy dialog. */
export const FEATURED_TEMPLATES = [
  'Classic 60/40',
  'All-Weather Portfolio',
  'Momentum Sectors',
  'Dual Momentum',
  'Risk Parity',
  'Pullback Buyer',
] as const;

/** The named templates in order, topped up from the catalog to `count`. */
export function pickTemplates(
  templates: readonly StrategyTemplate[],
  names: readonly string[],
  count: number
): StrategyTemplate[] {
  const byName = new Map(templates.map((t) => [t.name.toLowerCase(), t]));
  const picked = names
    .map((n) => byName.get(n.toLowerCase()))
    .filter((t): t is StrategyTemplate => t !== undefined)
    .slice(0, count);
  for (const t of templates) {
    if (picked.length >= count) break;
    if (!picked.includes(t)) picked.push(t);
  }
  return picked;
}

export function pickStarters(templates: readonly StrategyTemplate[]): StrategyTemplate[] {
  return pickTemplates(templates, STARTER_TEMPLATES, STARTER_TEMPLATES.length);
}

/** What a template holds as written in its first scenario, for drawing its holdings. */
export function templateHoldings(t: Pick<StrategyTemplate, 'configSexpr'>): WrittenHolding[] {
  const parsed = fromDSLString(t.configSexpr);
  if (!parsed) return [];
  return writtenScenarios(parsed.tree)[0]?.holdings ?? [];
}

/** "VOO 60 · BND 40" or "5 symbols" when the weights are ranked. */
export function holdingsShort(holdings: readonly WrittenHolding[]): string {
  if (!holdings.length) return '';
  if (holdings.every((h) => h.pct !== null) && holdings.length <= 3) {
    return holdings.map((h) => `${h.symbol} ${Math.round((h.pct ?? 0) * 10) / 10}`).join(' · ');
  }
  return `${holdings.length} ${holdings.length === 1 ? 'symbol' : 'symbols'}`;
}

export interface CategoryCount {
  category: TemplateCategory | 'all';
  count: number;
}

/** Counts per category from the loaded templates, "all" first, empty categories left out. */
export function categoryCounts(templates: readonly StrategyTemplate[]): CategoryCount[] {
  const counts = ALL_CATEGORIES.map((category) => ({
    category,
    count: templates.filter((t) => t.category === category).length,
  })).filter((c) => c.count > 0);
  return [{ category: 'all', count: templates.length }, ...counts];
}

/** Case-insensitive match on name, description, tags and held symbols. */
export function matchesTemplate(t: StrategyTemplate, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [t.name, t.description, ...t.tags, ...templateHoldings(t).map((h) => h.symbol)]
    .join(' ')
    .toLowerCase();
  return q.split(/\s+/).every((w) => hay.includes(w));
}
