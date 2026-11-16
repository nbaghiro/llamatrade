import { create } from '@bufbuild/protobuf';
import { StrategyTemplateSchema, TemplateCategory } from '@llamatrade/core/proto/strategy_pb';
import { describe, expect, it } from 'vitest';

import {
  categoryCounts,
  holdingsShort,
  matchesTemplate,
  pickStarters,
  pickTemplates,
  templateHoldings,
} from '../templateModel';

const tpl = (name: string, category: TemplateCategory, configSexpr: string, tags: string[] = []) =>
  create(StrategyTemplateSchema, {
    id: name.toLowerCase(),
    name,
    category,
    configSexpr,
    tags,
    description: `${name} template`,
  });

const SIXTY = tpl(
  'Classic 60/40',
  TemplateCategory.BUY_AND_HOLD,
  '(strategy "Classic 60/40" :rebalance quarterly (weight :method specified (asset VOO :weight 60) (asset BND :weight 40)))'
);
const MOM = tpl(
  'Momentum Sectors',
  TemplateCategory.FACTOR,
  '(strategy "Momentum Sectors" :rebalance monthly (weight :method momentum :lookback 126 :top 3 (asset XLK) (asset XLE) (asset XLF) (asset XLV)))',
  ['sectors']
);
const ALLW = tpl(
  'All-Weather Portfolio',
  TemplateCategory.BUY_AND_HOLD,
  '(strategy "AW" :rebalance quarterly (weight :method specified (asset VTI :weight 30) (asset TLT :weight 40) (asset IEF :weight 15) (asset GLD :weight 7.5) (asset DBC :weight 7.5)))'
);

describe('pickStarters', () => {
  it('takes the named starters in order and fills the rest from the catalog', () => {
    expect(pickStarters([MOM, ALLW, SIXTY]).map((t) => t.name)).toEqual([
      'Classic 60/40',
      'All-Weather Portfolio',
      'Momentum Sectors',
    ]);
  });

  it('returns what there is when the catalog is short', () => {
    expect(pickStarters([MOM])).toEqual([MOM]);
    expect(pickStarters([])).toEqual([]);
  });
});

describe('templateHoldings and holdingsShort', () => {
  it('reads fixed weights', () => {
    expect(templateHoldings(SIXTY)).toEqual([
      { symbol: 'VOO', pct: 60 },
      { symbol: 'BND', pct: 40 },
    ]);
    expect(holdingsShort(templateHoldings(SIXTY))).toBe('VOO 60 · BND 40');
  });

  it('counts symbols when weights are ranked or there are many', () => {
    expect(holdingsShort(templateHoldings(MOM))).toBe('4 symbols');
    expect(holdingsShort(templateHoldings(ALLW))).toBe('5 symbols');
  });

  it('is empty for text that does not parse', () => {
    expect(templateHoldings(tpl('Bad', TemplateCategory.TREND, '(oops'))).toEqual([]);
    expect(holdingsShort([])).toBe('');
  });
});

describe('categoryCounts', () => {
  it('counts each category from the data and leaves empty ones out', () => {
    expect(categoryCounts([SIXTY, ALLW, MOM])).toEqual([
      { category: 'all', count: 3 },
      { category: TemplateCategory.BUY_AND_HOLD, count: 2 },
      { category: TemplateCategory.FACTOR, count: 1 },
    ]);
  });
});

describe('matchesTemplate', () => {
  it('finds by name, tag and held symbol, every word', () => {
    expect(matchesTemplate(MOM, 'sectors')).toBe(true);
    expect(matchesTemplate(SIXTY, 'bnd')).toBe(true);
    expect(matchesTemplate(SIXTY, 'classic voo')).toBe(true);
    expect(matchesTemplate(SIXTY, 'classic xlk')).toBe(false);
    expect(matchesTemplate(SIXTY, '  ')).toBe(true);
  });
});

describe('pickTemplates', () => {
  it('caps at the count and keeps the named order', () => {
    expect(
      pickTemplates([MOM, ALLW, SIXTY], ['Momentum Sectors', 'Classic 60/40'], 1).map((t) => t.name)
    ).toEqual(['Momentum Sectors']);
  });
});
