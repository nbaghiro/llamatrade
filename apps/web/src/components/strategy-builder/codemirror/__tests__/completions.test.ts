// The editor may only advertise vocabulary the backend parser accepts. The tables
// come from @llamatrade/core/strategy/vocabulary, which tests/conformance/vocabulary.json
// (generated from libs/dsl) pins in the dsl-conformance suite.

import {
  DSL_BLOCK_TYPES,
  DSL_COMPARISON_OPS,
  DSL_CROSSOVER_OPS,
  DSL_FILTER_CRITERIA,
  DSL_INDICATORS,
  DSL_KEYWORD_SET,
  DSL_LOGICAL_OPS,
  DSL_METRICS,
  DSL_REBALANCE_FREQUENCIES,
  DSL_SELECT_DIRECTIONS,
  DSL_WEIGHT_METHODS,
} from '@llamatrade/core/strategy/vocabulary';
import { describe, expect, it } from 'vitest';

import { completionSets, formHeadAt, keywordsForForm } from '../completions';

const labels = (set: readonly { label: string }[]): string[] => set.map((c) => c.label);

describe('DSL completions stay inside the backend vocabulary', () => {
  it('block types are real block heads', () => {
    expect(DSL_BLOCK_TYPES).toEqual(expect.arrayContaining(labels(completionSets.blockTypes)));
  });

  it('parameters are real keyword arguments', () => {
    for (const label of labels(completionSets.parameters)) {
      expect(DSL_KEYWORD_SET.has(label), `${label} is not a DSL keyword`).toBe(true);
    }
  });

  it('weight methods are accepted methods', () => {
    expect(DSL_WEIGHT_METHODS).toEqual(
      expect.arrayContaining(labels(completionSets.weightMethods))
    );
  });

  it('filter selection and criteria match the grammar', () => {
    expect(labels(completionSets.filterMethods).sort()).toEqual([...DSL_SELECT_DIRECTIONS]);
    expect(labels(completionSets.sortCriteria).sort()).toEqual([...DSL_FILTER_CRITERIA]);
  });

  it('rebalance frequencies match the grammar', () => {
    expect(labels(completionSets.rebalanceFrequencies).sort()).toEqual([
      ...DSL_REBALANCE_FREQUENCIES,
    ]);
  });

  it('indicators match the grammar exactly', () => {
    expect(labels(completionSets.indicators).sort()).toEqual([...DSL_INDICATORS]);
  });

  it('value functions are price plus the metrics', () => {
    expect(labels(completionSets.metrics).sort()).toEqual(['price', ...DSL_METRICS].sort());
  });

  it('operators match the comparison and crossover sets', () => {
    expect(labels(completionSets.operators).sort()).toEqual(
      [...DSL_COMPARISON_OPS, ...DSL_CROSSOVER_OPS].sort()
    );
  });

  it('logical operators match the grammar', () => {
    expect(labels(completionSets.logicalOps).sort()).toEqual([...DSL_LOGICAL_OPS]);
  });

  it('offers no retired keyword', () => {
    const retired = [
      ':name',
      ':symbol',
      ':symbols',
      ':entry',
      ':exit',
      ':children',
      ':lookback-days',
      ':selection',
      ':count',
      ':sort-by',
      ':universe',
      ':period',
      ':type',
      ':position-size',
      ':stop-loss-pct',
      ':take-profit-pct',
      'allocation',
      'then',
      'cross-above',
      'cross-below',
      'market_cap',
      'dividend_yield',
    ];
    const offered = new Set(Object.values(completionSets).flatMap(labels));
    for (const label of retired) {
      expect(offered.has(label), `${label} is still offered`).toBe(false);
    }
  });
});

describe('keyword completions follow the form at the cursor', () => {
  const code = '(strategy "S" :rebalance monthly\n  (weight :method momentum :';
  const at = (text: string) => formHeadAt(text, text.length);

  it('finds the innermost open form', () => {
    expect(at(code)).toBe('weight');
    expect(at('(strategy "S" :')).toBe('strategy');
    expect(at('(strategy "S" (if (> (rsi SPY 14) 70) (asset TLT :')).toBe('asset');
    expect(at('')).toBeNull();
  });

  it('skips forms that are already closed', () => {
    expect(at('(strategy "S" (asset TLT) :')).toBe('strategy');
  });

  it('ignores parentheses inside strings', () => {
    expect(at('(strategy "a (weight" :')).toBe('strategy');
  });

  it('offers only the keywords a weight accepts', () => {
    expect(labels(keywordsForForm('weight')).sort()).toEqual([':lookback', ':method', ':top']);
  });

  it('offers the strategy keywords at the top form', () => {
    expect(labels(keywordsForForm('strategy')).sort()).toEqual([
      ':benchmark',
      ':description',
      ':rebalance',
    ]);
  });

  it('offers nothing where no keyword is accepted', () => {
    expect(keywordsForForm('if')).toEqual([]);
    expect(keywordsForForm(null)).toEqual([]);
  });

  it('lists market-cap as unavailable and last', () => {
    const cap = completionSets.weightMethods.find((m) => m.label === 'market-cap');
    expect(cap?.detail).toBe('not supported');
    expect(cap?.boost).toBeLessThan(0);
    expect(labels(completionSets.weightMethods).sort()).toEqual([...DSL_WEIGHT_METHODS]);
  });
});
