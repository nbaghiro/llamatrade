import { blockForms, formPathAt, readForms, rowRanges } from '@llamatrade/core/strategy/forms';
import { fromDSLString, toDSL } from '@llamatrade/core/strategy/serializer';
import { describe, expect, it } from 'vitest';

import { blockOrder, codeTokens, splitRows } from '../rows';

const SOURCE = `(strategy "Recession Radar"
  :rebalance monthly
  :benchmark SPY
  (if (> (rsi SPY 14) 72)
    (weight :method specified
      (asset TLT :weight 60)
      (asset GLD :weight 40))
    (else
      (weight :method momentum :lookback 120 :top 2
        (asset VTI)
        (asset QQQ)
        (asset SMH)
        (asset IWM)))))`;

function serialized() {
  const parsed = fromDSLString(SOURCE);
  if (!parsed) throw new Error('fixture does not parse');
  const code = toDSL(parsed.tree, {
    name: 'Recession Radar',
    timeframe: parsed.metadata.timeframe ?? '1D',
    benchmark: parsed.metadata.benchmark,
  });
  return { tree: parsed.tree, code };
}

describe('readForms', () => {
  it('reads heads, lines, keywords and children', () => {
    const forms = readForms(SOURCE);
    const weight = forms.find((f) => f.head === 'weight' && f.keywords.includes('top'));
    expect(weight?.keywords).toEqual(['method', 'lookback', 'top']);
    expect(weight?.blockChildren).toBe(4);
    expect(weight?.startLine).toBe(9);
    expect(forms[0].head).toBe('strategy');
    expect(forms[0].keywords).toEqual(['rebalance', 'benchmark']);
    expect(forms.every((f) => f.closed)).toBe(true);
  });

  it('finds the path to an offset', () => {
    const offset = SOURCE.indexOf('(asset SMH') + 3;
    const path = formPathAt(readForms(SOURCE), offset).map((f) => f.head);
    expect(path).toEqual(['strategy', 'if', 'else', 'weight', 'asset']);
  });

  it('keeps unclosed forms open to the end', () => {
    const forms = readForms('(strategy "S" (weight :method');
    expect(forms.map((f) => f.closed)).toEqual([false, false]);
    expect(formPathAt(forms, 29).map((f) => f.head)).toEqual(['strategy', 'weight']);
  });
});

describe('rowRanges', () => {
  it('gives each anchor the lines up to the next one', () => {
    expect(rowRanges([1, 4, 8], 14)).toEqual([
      { from: 1, to: 3 },
      { from: 4, to: 7 },
      { from: 8, to: 14 },
    ]);
  });
});

describe('splitRows', () => {
  it('lines the serializer’s block forms up with the tree’s reading order', () => {
    const { tree, code } = serialized();
    const heads = blockForms(readForms(code)).map((f) => f.head);
    expect(heads).toEqual(blockOrder(tree).map((id) => tree.blocks[id].type));
  });

  it('puts settings first, then one row per rule with its holdings inside', () => {
    const { tree, code } = serialized();
    const rows = splitRows(tree, code);
    expect(rows).not.toBeNull();
    if (!rows) return;
    expect(rows[0].kind).toBe('settings');
    expect(rows[0].code.from).toBe(1);
    const kinds = rows.slice(1).map((r) => r.lines.map((l) => l.kind));
    expect(kinds).toEqual([
      ['if'],
      ['weight', 'asset', 'asset'],
      ['else'],
      ['weight', 'asset', 'asset', 'asset', 'asset'],
    ]);
    const lines = code.split('\n');
    for (const row of rows.slice(1)) {
      const first = lines[row.code.from - 1];
      expect(first).toContain(`(${row.lines[0].kind}`);
    }
    expect(rows[rows.length - 1].code.to).toBe(lines.length);
  });

  it('covers every code line exactly once', () => {
    const { tree, code } = serialized();
    const rows = splitRows(tree, code) ?? [];
    const covered = rows.flatMap((r) =>
      Array.from({ length: Math.max(0, r.code.to - r.code.from + 1) }, (_, i) => r.code.from + i)
    );
    expect(covered).toEqual(Array.from({ length: code.split('\n').length }, (_, i) => i + 1));
  });

  it('gives up when the code no longer matches the tree', () => {
    const { tree, code } = serialized();
    expect(splitRows(tree, code.replace('(asset IWM)', ''))).toBeNull();
  });
});

describe('codeTokens', () => {
  it('colours heads, keywords, strings and numbers', () => {
    const t = codeTokens('  (weight :method momentum :lookback 120 "x y")');
    expect(t.filter((x) => x.kind === 'head').map((x) => x.text)).toEqual(['weight']);
    expect(t.filter((x) => x.kind === 'keyword').map((x) => x.text)).toEqual([
      ':method',
      ':lookback',
    ]);
    expect(t.filter((x) => x.kind === 'number').map((x) => x.text)).toEqual(['120']);
    expect(t.filter((x) => x.kind === 'string').map((x) => x.text)).toEqual(['"x y"']);
    expect(t.map((x) => x.text).join('')).toBe('  (weight :method momentum :lookback 120 "x y")');
  });
});
