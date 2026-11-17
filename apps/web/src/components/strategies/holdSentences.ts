/** The rules read as sentences (holdings2 A), from the written scenarios, not an evaluation. */

import type { StrategyTree } from '@llamatrade/core/strategy/types';

import {
  buildOutline,
  lineText,
  methodWords,
  writtenScenarios,
  type WrittenHolding,
  type WrittenScenario,
} from '../../lib/outline';

export interface HoldSentence {
  /** "When the 14-day RSI of SPY is above 70", "Otherwise", or null when there are no rules. */
  when: string | null;
  scenario: WrittenScenario;
}

const pct = (v: number) => `${Math.round(v * 10) / 10}%`;

/** "A, B and C". */
export function listWords(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? '';
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** "TLT 60% and GLD 40%", or "VTI, QQQ and IWM, weighted by momentum at each rebalance". */
export function holdingWords(scenario: Pick<WrittenScenario, 'holdings' | 'rankedBy'>): string {
  const fixed = scenario.holdings.filter(
    (h): h is WrittenHolding & { pct: number } => h.pct !== null
  );
  const ranked = scenario.holdings.filter((h) => h.pct === null).map((h) => h.symbol);
  const parts = fixed.map((h) => `${h.symbol} ${pct(h.pct)}`);
  if (ranked.length) {
    const how = scenario.rankedBy.length
      ? `weighted by ${listWords(scenario.rankedBy.map(methodWords))} at each rebalance`
      : 'weighted at each rebalance';
    const named =
      ranked.length > 5
        ? `${ranked.slice(0, 4).join(', ')} and ${ranked.length - 4} more`
        : listWords(ranked);
    parts.push(`${named}, ${how}`);
  }
  return parts.length ? listWords(parts) : 'nothing';
}

/** Each branch the strategy can take, with the condition that leads to it in words. */
export function holdSentences(tree: StrategyTree): HoldSentence[] {
  const scenarios = writtenScenarios(tree);
  const conditions = buildOutline(tree)
    .filter((l) => l.kind === 'if')
    .map((l) => lineText(l).replace(/^If\s+/i, ''));
  if (scenarios.length === 1 && scenarios[0].label === 'Always') {
    return [{ when: null, scenario: scenarios[0] }];
  }
  if (conditions.length === 1 && scenarios.length === 2) {
    return [
      { when: `When ${conditions[0]}`, scenario: scenarios[0] },
      { when: 'Otherwise', scenario: scenarios[1] },
    ];
  }
  return scenarios.map((s) => ({ when: s.label.replace(/^If /, 'When '), scenario: s }));
}
