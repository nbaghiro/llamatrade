import { describe, expect, it } from 'vitest';

import { TAPE_ITEMS } from '../../config/marketing';
import { EDITOR_LEVELS } from '../data/editorLevels';
import { accountMonth, INDICATORS, METRICS } from '../data/illustrative';
import { highlightDsl } from '../lib/dsl';
import { chartArt, levelLabel, SECTION_SHAPES, sectionBox } from '../lib/sectionArt';
import { walk, walkPath } from '../lib/shapes';
import { splitRule } from '../lib/tape';

describe('chartArt', () => {
  const box = { width: 1440, top: 40, height: 320 };

  it('draws nothing at zero size', () => {
    expect(chartArt(SECTION_SHAPES.build, { ...box, width: 0 })).toEqual([]);
    expect(chartArt(SECTION_SHAPES.build, { ...box, height: 0 })).toEqual([]);
  });

  it('is the same on every run', () => {
    expect(chartArt(SECTION_SHAPES.copilot, box)).toEqual(chartArt(SECTION_SHAPES.copilot, box));
  });

  it('gives every shape a body, levels and a drawn-in accent', () => {
    for (const shape of Object.values(SECTION_SHAPES)) {
      const groups = chartArt(shape, box);
      expect(groups.map((g) => g.className)).toEqual(['sa sabody', 'sa', 'sa acc']);
      expect(groups[2].paint).toBe('accent');
      expect(groups[2].shapes.some((s) => s.kind === 'path' && s.draw)).toBe(true);
      expect(groups[0].shapes.length).toBeGreaterThan(0);
    }
  });

  it('keeps every shape inside the art width', () => {
    for (const shape of Object.values(SECTION_SHAPES)) {
      for (const g of chartArt(shape, box))
        for (const s of g.shapes) {
          if (s.kind === 'rect') expect(s.x + s.w).toBeLessThanOrEqual(box.width + 0.1);
          if (s.kind === 'line') expect(Math.max(s.x1, s.x2)).toBeLessThanOrEqual(box.width);
        }
    }
  });

  it('uses a different seed for every section', () => {
    const seeds = Object.values(SECTION_SHAPES).map((s) => s.seed);
    expect(new Set(seeds).size).toBe(seeds.length);
  });

  it('labels levels as dollars for account-sized bases and as prices otherwise', () => {
    expect(levelLabel(103410.4, 103410)).toBe('$103,410');
    expect(levelLabel(612.5, 612.5)).toBe('612.50');
  });

  it('fits the price band under the section and above its bottom', () => {
    const { height, box: b } = sectionBox(1440, 900, 190);
    expect(height).toBe(650);
    expect(b.top).toBe(24);
    expect(b.height).toBe(400);
    expect(sectionBox(1440, 300, 190).height).toBe(300);
  });
});

describe('walk and walkPath', () => {
  it('stays inside 0.05 to 0.95', () => {
    let i = 0;
    const r = () => [0, 1][i++ % 2];
    for (const v of walk(r, 50, 0.3, 2)) {
      expect(v).toBeGreaterThanOrEqual(0.05);
      expect(v).toBeLessThanOrEqual(0.95);
    }
  });

  it('runs from the left edge to the right edge of the box', () => {
    expect(walkPath([1, 0], 10, 20, 100, 50)).toBe('M10,20L110,70');
  });
});

describe('highlightDsl', () => {
  it('marks block keywords after "(" and quoted strings', () => {
    expect(highlightDsl('(strategy "Core Four"')).toEqual([
      { text: '(' },
      { text: 'strategy', tone: 'keyword' },
      { text: ' ' },
      { text: '"Core Four"', tone: 'string' },
    ]);
  });

  it('leaves functions and options plain', () => {
    const toks = highlightDsl('  (if (> (rsi SPY 14) 70)');
    expect(toks.filter((t) => t.tone).map((t) => t.text)).toEqual(['if']);
    expect(toks.map((t) => t.text).join('')).toBe('  (if (> (rsi SPY 14) 70)');
  });

  it('keeps the line text intact', () => {
    for (const level of EDITOR_LEVELS)
      for (const line of level.code)
        expect(
          highlightDsl(line)
            .map((t) => t.text)
            .join('')
        ).toBe(line);
  });
});

describe('screen data', () => {
  it('lists the 17 indicators of the strategy language (libs/dsl INDICATORS)', () => {
    expect(INDICATORS).toHaveLength(17);
    expect(new Set(INDICATORS).size).toBe(17);
    expect(METRICS).toEqual(['return', 'volatility', 'drawdown']);
  });

  it('has a Starter, Tactical and Advanced level, each holding 100%', () => {
    expect(EDITOR_LEVELS.map((l) => l.tab)).toEqual(['Starter', 'Tactical', 'Advanced']);
    for (const l of EDITOR_LEVELS)
      expect(l.hold.reduce((a, h) => a + h.weight, 0)).toBeCloseTo(100, 6);
  });

  it('ends the illustrative account month on the screen figures', () => {
    const m = accountMonth();
    expect(m.days.length).toBe(m.account.length);
    expect(m.account[0]).toBeCloseTo(101_284.6, 2);
    expect(m.account[m.account.length - 1]).toBeCloseTo(103_410.27, 2);
  });
});

describe('tape', () => {
  it('splits a rule into the paren, the operator and the rest', () => {
    expect(splitRule('(sma SPY 200)')).toEqual(['(', 'sma', ' SPY 200)']);
    expect(splitRule('plain')).toEqual(['', '', 'plain']);
  });

  it('writes every rule for its own symbol', () => {
    for (const t of TAPE_ITEMS) expect(t.rule).toContain(` ${t.symbol} `);
  });
});
