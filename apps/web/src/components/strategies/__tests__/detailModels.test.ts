import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import {
  StrategyTemplateSchema,
  TemplateCategory,
  TemplateDifficulty,
} from '@llamatrade/core/proto/strategy_pb';
import { OrderSchema, OrderSide, OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { describe, expect, it } from 'vitest';

import { fillDays, toFills } from '../detail/fills';
import { toTab } from '../detail/tabs';
import { holdingWords, holdSentences, listWords } from '../holdSentences';
import { longestRun } from '../strategyView';
import { barShares, goalTemplates, isFixedMix, pickThree, templateGoals } from '../templateModel';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

const RADAR = `(strategy "Radar" :rebalance monthly :benchmark SPY
  (if (> (rsi SPY 14) 70)
    (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
    (else (weight :method momentum :lookback 90 (asset VTI) (asset QQQ) (asset IWM)))))`;
const FIXED = `(strategy "60/40" :rebalance quarterly
  (weight :method specified (asset VTI :weight 60) (asset BND :weight 40)))`;

const tree = (dsl: string) => {
  const parsed = fromDSLString(dsl);
  if (!parsed) throw new Error('fixture does not parse');
  return parsed.tree;
};

describe('holdSentences', () => {
  it('reads one rule as "when" and "otherwise"', () => {
    const [a, b] = holdSentences(tree(RADAR));
    expect(a.when).toBe('When the 14-day RSI of SPY is above 70');
    expect(holdingWords(a.scenario)).toBe('TLT 60% and GLD 40%');
    expect(b.when).toBe('Otherwise');
    expect(holdingWords(b.scenario)).toBe(
      'VTI, QQQ and IWM, weighted by momentum at each rebalance'
    );
  });

  it('has no condition for fixed weights', () => {
    const [only, ...rest] = holdSentences(tree(FIXED));
    expect(only.when).toBeNull();
    expect(rest).toEqual([]);
    expect(holdingWords(only.scenario)).toBe('VTI 60% and BND 40%');
  });

  it('shortens a long ranked list', () => {
    expect(
      holdingWords({
        holdings: ['A', 'B', 'C', 'D', 'E', 'F'].map((symbol) => ({ symbol, pct: null })),
        rankedBy: [],
      })
    ).toBe('A, B, C, D and 2 more, weighted at each rebalance');
  });

  it('joins words naturally', () => {
    expect(listWords([])).toBe('');
    expect(listWords(['A'])).toBe('A');
    expect(listWords(['A', 'B', 'C'])).toBe('A, B and C');
  });
});

const template = (over: {
  name: string;
  category: TemplateCategory;
  difficulty?: TemplateDifficulty;
  tags?: string[];
  dsl?: string;
}) =>
  create(StrategyTemplateSchema, {
    id: over.name,
    name: over.name,
    category: over.category,
    difficulty: over.difficulty ?? TemplateDifficulty.BEGINNER,
    tags: over.tags ?? [],
    configSexpr: over.dsl ?? RADAR,
  });

describe('template goals', () => {
  const fixed = template({ name: '60/40', category: TemplateCategory.BUY_AND_HOLD, dsl: FIXED });
  const defensive = template({
    name: 'Defensive',
    category: TemplateCategory.TACTICAL,
    difficulty: TemplateDifficulty.ADVANCED,
    tags: ['defensive'],
  });
  const trend = template({
    name: 'Trend',
    category: TemplateCategory.TREND,
    difficulty: TemplateDifficulty.INTERMEDIATE,
  });
  const income = template({
    name: 'Income',
    category: TemplateCategory.INCOME,
    tags: ['dividends'],
  });
  const allWeather = template({
    name: 'All-Weather',
    category: TemplateCategory.BUY_AND_HOLD,
    tags: ['all-weather'],
    dsl: FIXED,
  });

  it('assigns goals from category, tags and rules', () => {
    expect(isFixedMix(fixed)).toBe(true);
    expect(isFixedMix(trend)).toBe(false);
    expect(templateGoals(fixed)).toEqual(['fixed']);
    expect(templateGoals(defensive)).toEqual(['downturns']);
    expect(templateGoals(trend)).toEqual(['trends']);
    expect(templateGoals(income)).toEqual(['income']);
    expect(templateGoals(allWeather)).toEqual(['downturns', 'fixed']);
  });

  it('lists a goal simplest first and picks one per approach', () => {
    const all = [defensive, fixed, trend, allWeather];
    expect(goalTemplates(all, 'downturns').map((t) => t.name)).toEqual([
      'All-Weather',
      'Defensive',
    ]);
    expect(goalTemplates(all, 'fixed').map((t) => t.name)).toEqual(['60/40', 'All-Weather']);
    expect(pickThree([fixed, allWeather, trend, defensive]).map((t) => t.name)).toEqual([
      '60/40',
      'Trend',
      'Defensive',
    ]);
    expect(pickThree([fixed, allWeather]).map((t) => t.name)).toEqual(['60/40', 'All-Weather']);
  });

  it('splits what fixed weights leave among ranked holdings', () => {
    expect(
      barShares([
        { symbol: 'A', pct: 40 },
        { symbol: 'B', pct: null },
        { symbol: 'C', pct: null },
      ])
    ).toEqual([
      { symbol: 'A', pct: 40 },
      { symbol: 'B', pct: 30 },
      { symbol: 'C', pct: 30 },
    ]);
  });
});

describe('fills', () => {
  const order = (id: string, at: string, status = OrderStatus.FILLED, side = OrderSide.BUY) =>
    create(OrderSchema, {
      id,
      symbol: 'TLT',
      side,
      status,
      quantity: { value: '10' },
      filledQuantity: { value: '10' },
      averageFillPrice: { value: '90' },
      filledAt: ts(at),
    });

  it('keeps filled orders and groups them by New York day, sells first', () => {
    const fills = toFills([
      order('a', '2026-11-03T15:00:00Z'),
      order('b', '2026-11-03T15:01:00Z', OrderStatus.FILLED, OrderSide.SELL),
      order('c', '2026-11-04T02:00:00Z'),
      order('d', '2026-11-05T15:00:00Z', OrderStatus.REJECTED),
    ]);
    expect(fills).toHaveLength(3);
    expect(fills[0].notional).toBe(900);
    const days = fillDays(fills);
    expect(days.map((x) => x.day.toISOString().slice(0, 10))).toEqual(['2026-11-03']);
    expect(days[0].fills.map((f) => f.id)).toEqual(['b', 'a', 'c']);
  });
});

describe('toTab', () => {
  it('maps old tab names to the new ones', () => {
    expect(toTab(undefined)).toBe('overview');
    expect(toTab('rules')).toBe('rules');
    expect(toTab('definition')).toBe('rules');
    expect(toTab('backtests')).toBe('performance');
    expect(toTab('session')).toBe('overview');
    expect(toTab('nonsense')).toBe('overview');
  });
});

describe('longestRun', () => {
  const run = (id: string, version: number, start: string, status = BacktestStatus.COMPLETED) =>
    create(BacktestRunSchema, {
      id,
      strategyVersion: version,
      status,
      config: { startDate: ts(start), endDate: ts('2026-10-01T00:00:00Z') },
    });

  it('prefers the current version, then the longest range', () => {
    const runs = [
      run('a', 1, '2010-01-01T00:00:00Z'),
      run('b', 2, '2020-01-01T00:00:00Z'),
      run('c', 2, '2018-01-01T00:00:00Z'),
      run('d', 2, '2000-01-01T00:00:00Z', BacktestStatus.FAILED),
    ];
    expect(longestRun(runs, 2)?.id).toBe('c');
    expect(longestRun(runs, 3)?.id).toBe('a');
    expect(longestRun([], 1)).toBeNull();
  });
});
