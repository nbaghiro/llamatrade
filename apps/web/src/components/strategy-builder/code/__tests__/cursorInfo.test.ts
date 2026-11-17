import { readForms } from '@llamatrade/core/strategy/forms';
import { describe, expect, it } from 'vitest';

import { cursorInfo, fileName, keywordRows, keywordValues } from '../cursorInfo';

const CODE = `(strategy "Recession Radar"
  :rebalance monthly
  :benchmark SPY
  (if (> (rsi SPY 14) 72)
    (weight :method specified
      (asset TLT :weight 60)
      (asset GLD :weight 40))
    (else
      (weight :method momentum :lookback 120
        (asset VTI)
        (asset QQQ)))))`;

const at = (needle: string, shift = 1) => CODE.indexOf(needle) + shift;

describe('cursorInfo', () => {
  const forms = readForms(CODE);

  it('describes a weight on the otherwise side', () => {
    const info = cursorInfo(CODE, forms, at(':method momentum'));
    expect(info.crumbs).toEqual(['strategy', 'if', 'else', 'weight']);
    expect(info.place).toBe('on the otherwise side');
    expect(info.accepts).toEqual([':lookback', ':method', ':top']);
    expect(info.set).toEqual([
      { name: 'method', value: 'momentum' },
      { name: 'lookback', value: '120' },
    ]);
    expect(info.missing).toEqual([':top']);
    expect(info.children).toBe('2 assets');
  });

  it('skips condition forms in the breadcrumb', () => {
    const info = cursorInfo(CODE, forms, at('(rsi SPY', 3));
    expect(info.crumbs).toEqual(['strategy', 'if']);
    expect(info.accepts).toEqual([]);
    expect(info.children).toBe('2 blocks');
  });

  it('reads the strategy settings, ignoring nested keywords', () => {
    const info = cursorInfo(CODE, forms, at(':benchmark'));
    expect(info.form?.head).toBe('strategy');
    expect(info.set.map((k) => k.name)).toEqual(['rebalance', 'benchmark']);
    expect(info.missing).toEqual([':description']);
  });

  it('is empty outside every form', () => {
    expect(cursorInfo(CODE, forms, 0).form).toBeNull();
  });
});

describe('keywordValues', () => {
  it('reads string and form values', () => {
    const code = '(strategy "S" :description "a (b) c" :rebalance weekly)';
    const [f] = readForms(code);
    expect(keywordValues(code, f)).toEqual([
      { name: 'description', value: '"a (b) c"' },
      { name: 'rebalance', value: 'weekly' },
    ]);
  });
});

describe('keywordRows and fileName', () => {
  it('merges forms with the same keywords', () => {
    expect(keywordRows()).toContainEqual({ forms: 'asset, group', keywords: ':weight' });
  });

  it('slugs the strategy name', () => {
    expect(fileName('Recession Radar')).toBe('recession-radar.lt');
    expect(fileName('  ')).toBe('strategy.lt');
  });
});
