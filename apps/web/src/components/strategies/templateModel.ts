import {
  TemplateCategory,
  TemplateDifficulty,
  type StrategyTemplate,
} from '@llamatrade/core/proto/strategy_pb';
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

export type GoalKey = 'downturns' | 'trends' | 'income' | 'growth' | 'fixed';

export interface Goal {
  key: GoalKey;
  title: string;
  body: string;
}

/** The five goals the gallery opens on (templates2 A). */
export const GOALS: readonly Goal[] = [
  {
    key: 'downturns',
    title: 'Hold up in downturns',
    body: 'Gives up some growth to fall less when markets drop.',
  },
  {
    key: 'trends',
    title: 'Follow trends',
    body: 'Holds what has been rising and steps aside when it stops.',
  },
  { key: 'income', title: 'Steady income', body: 'Dividends and interest paid along the way.' },
  {
    key: 'growth',
    title: 'Grow over the long run',
    body: 'Mostly stocks, held for years, with few trades.',
  },
  {
    key: 'fixed',
    title: 'A mix that rarely changes',
    body: 'Fixed weights, rebalanced on a schedule.',
  },
];

const DOWNTURN_TAGS = new Set([
  'defensive',
  'all-weather',
  'crash-protection',
  'tail-risk',
  'hedged',
  'protective',
  'risk-management',
  'risk-parity',
  'defensive-momentum',
  'canary',
]);
const TREND_TAGS = new Set(['trend', 'momentum', 'dual-momentum', 'breakout']);
const INCOME_TAGS = new Set(['dividends', 'dividend', 'income', 'premium-income']);
const GROWTH_TAGS = new Set(['bogleheads', 'core-satellite', 'growth']);

/** Fixed weights in a single branch: nothing in the rules decides what to hold. */
export function isFixedMix(t: Pick<StrategyTemplate, 'configSexpr'>): boolean {
  const parsed = fromDSLString(t.configSexpr);
  if (!parsed) return false;
  const scenarios = writtenScenarios(parsed.tree);
  return (
    scenarios.length === 1 &&
    scenarios[0].holdings.length > 0 &&
    scenarios[0].holdings.every((h) => h.pct !== null)
  );
}

/** The goals a template serves, from its category, tags and rules. */
export function templateGoals(
  t: Pick<StrategyTemplate, 'category' | 'tags' | 'configSexpr'>
): GoalKey[] {
  const tags = t.tags.map((x) => x.toLowerCase());
  const has = (set: ReadonlySet<string>) => tags.some((x) => set.has(x));
  const out: GoalKey[] = [];
  if (has(DOWNTURN_TAGS)) out.push('downturns');
  if (t.category === TemplateCategory.TREND || has(TREND_TAGS)) out.push('trends');
  if (t.category === TemplateCategory.INCOME || has(INCOME_TAGS)) out.push('income');
  if (t.category === TemplateCategory.FACTOR || has(GROWTH_TAGS)) out.push('growth');
  if (isFixedMix(t)) out.push('fixed');
  return out;
}

const DIFFICULTY_ORDER: Record<TemplateDifficulty, number> = {
  [TemplateDifficulty.BEGINNER]: 0,
  [TemplateDifficulty.INTERMEDIATE]: 1,
  [TemplateDifficulty.ADVANCED]: 2,
  [TemplateDifficulty.UNSPECIFIED]: 3,
};

/** Every template for a goal, simplest first, catalog order within a difficulty. */
export function goalTemplates(
  templates: readonly StrategyTemplate[],
  goal: GoalKey
): StrategyTemplate[] {
  return templates
    .map((t, i) => ({ t, i }))
    .filter(({ t }) => templateGoals(t).includes(goal))
    .sort(
      (a, b) => DIFFICULTY_ORDER[a.t.difficulty] - DIFFICULTY_ORDER[b.t.difficulty] || a.i - b.i
    )
    .map(({ t }) => t);
}

/** Up to three, one from each approach (category) first, in the order given. */
export function pickThree(templates: readonly StrategyTemplate[]): StrategyTemplate[] {
  const out: StrategyTemplate[] = [];
  const cats = new Set<TemplateCategory>();
  for (const t of templates) {
    if (out.length >= 3) break;
    if (cats.has(t.category)) continue;
    cats.add(t.category);
    out.push(t);
  }
  for (const t of templates) {
    if (out.length >= 3) break;
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

/** Bar shares for written holdings: ranked ones split what the fixed ones leave, evenly. */
export function barShares(holdings: readonly WrittenHolding[]): { symbol: string; pct: number }[] {
  const fixedTotal = holdings.reduce((s, h) => s + (h.pct ?? 0), 0);
  const ranked = holdings.filter((h) => h.pct === null).length;
  const each = ranked ? Math.max(0, 100 - fixedTotal) / ranked : 0;
  return holdings.map((h) => ({ symbol: h.symbol, pct: h.pct ?? each }));
}
