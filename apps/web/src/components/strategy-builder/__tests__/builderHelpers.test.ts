import { create } from '@bufbuild/protobuf';
import { BacktestConfigSchema } from '@llamatrade/core/proto/backtest_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TradeInput } from '../../../lib/backtestView';
import { diffCode } from '../../../lib/strategyDiff';
import { changedHunk } from '../copilot/hunk';
import { clearLocalDraft, readLocalDraft, writeLocalDraft } from '../draft/localDraft';
import { defaultSettings, handoffConfig } from '../handoff/useHandoffRun';
import { conditionSides, sideSpans, sidesAtRebalances } from '../history/sides';
import { questionsFirstPrompt } from '../start/draftPrompts';

const RADAR = `(strategy "Recession Radar"
  :rebalance monthly
  :benchmark SPY
  (if (> (rsi SPY 14) 70)
    (weight :method specified
      (asset TLT :weight 60)
      (asset GLD :weight 40))
    (else
      (weight :method momentum :lookback 90 :top 2
        (asset VTI)
        (asset QQQ)))))`;

const tree = () => {
  const parsed = fromDSLString(RADAR);
  if (!parsed) throw new Error('fixture does not parse');
  return parsed.tree;
};

const trade = (symbol: string, entry: string, exit: string | null): TradeInput => ({
  symbol,
  side: 'BUY',
  quantity: 1,
  entryPrice: 1,
  exitPrice: 1,
  entryTime: new Date(`${entry}T15:00:00Z`),
  exitTime: exit ? new Date(`${exit}T15:00:00Z`) : null,
  pnl: 0,
  entryReason: '',
  exitReason: '',
});

describe('conditionSides', () => {
  it('reads the symbols on each side of the first if/else', () => {
    const sides = conditionSides(tree());
    expect(sides).not.toBeNull();
    expect([...(sides?.when ?? [])].sort()).toEqual(['GLD', 'TLT']);
    expect([...(sides?.otherwise ?? [])].sort()).toEqual(['QQQ', 'VTI']);
    expect(sides?.condition).toContain('70');
  });

  it('gives up when both sides hold the same symbol', () => {
    const parsed = fromDSLString(RADAR.replace('(asset QQQ)', '(asset TLT)'));
    expect(parsed && conditionSides(parsed.tree)).toBeNull();
  });

  it('is null for a strategy without a condition', () => {
    const parsed = fromDSLString(
      '(strategy "Mix" :rebalance monthly (weight :method equal (asset SPY) (asset BND)))'
    );
    expect(parsed && conditionSides(parsed.tree)).toBeNull();
  });
});

describe('sidesAtRebalances', () => {
  const sides = { when: new Set(['TLT', 'GLD']), otherwise: new Set(['VTI', 'QQQ']) };

  it('labels each trading day by what was held at its end', () => {
    const points = sidesAtRebalances(
      [
        trade('VTI', '2025-01-02', '2025-02-03'),
        trade('QQQ', '2025-01-02', '2025-02-03'),
        trade('TLT', '2025-02-03', '2025-03-03'),
        trade('VTI', '2025-03-03', null),
      ],
      sides
    );
    expect(points.map((p) => p.side)).toEqual(['otherwise', 'when', 'otherwise']);
  });

  it('marks a day that holds both sides as unknown', () => {
    const points = sidesAtRebalances(
      [trade('VTI', '2025-01-02', null), trade('TLT', '2025-01-02', null)],
      sides
    );
    expect(points).toHaveLength(1);
    expect(points[0].side).toBeNull();
  });

  it('returns nothing without trades', () => {
    expect(sidesAtRebalances([], sides)).toEqual([]);
  });
});

describe('sideSpans', () => {
  it('joins consecutive days on one side and runs to the next change', () => {
    const d = (s: string) => new Date(`${s}T12:00:00Z`);
    const spans = sideSpans(
      [
        { date: d('2025-01-02'), side: 'when' },
        { date: d('2025-02-03'), side: 'when' },
        { date: d('2025-03-03'), side: 'otherwise' },
        { date: d('2025-04-01'), side: null },
      ],
      d('2025-05-01')
    );
    expect(spans).toEqual([
      { side: 'when', from: d('2025-01-02'), to: d('2025-03-03') },
      { side: 'otherwise', from: d('2025-03-03'), to: d('2025-04-01') },
    ]);
  });
});

describe('localDraft', () => {
  beforeEach(() => {
    const data = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('round-trips a draft and clears it', () => {
    writeLocalDraft({ dsl: RADAR, name: 'Radar' }, 42);
    expect(readLocalDraft()).toEqual({ dsl: RADAR, name: 'Radar', savedAt: 42 });
    clearLocalDraft();
    expect(readLocalDraft()).toBeNull();
  });

  it('ignores an empty or malformed entry', () => {
    localStorage.setItem('llamatrade-builder-draft', '{"dsl":"  ","name":"x","savedAt":1}');
    expect(readLocalDraft()).toBeNull();
    localStorage.setItem('llamatrade-builder-draft', 'not json');
    expect(readLocalDraft()).toBeNull();
  });

  it('survives blocked storage', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    });
    expect(() => writeLocalDraft({ dsl: RADAR, name: 'x' })).not.toThrow();
    expect(readLocalDraft()).toBeNull();
    expect(() => clearLocalDraft()).not.toThrow();
  });
});

describe('handoffConfig', () => {
  it('reuses the base run and changes only the version', () => {
    const base = handoffConfig('s1', 3, undefined, new Date('2026-11-16T00:00:00Z'));
    const next = handoffConfig('s1', 4, create(BacktestConfigSchema, base));
    expect(next.strategyVersion).toBe(4);
    expect(next.startDate?.seconds).toBe(base.startDate?.seconds);
    expect(next.initialCapital?.value).toBe(base.initialCapital?.value);
  });

  it('falls back to two years and $10,000 without a base run', () => {
    const d = defaultSettings(new Date('2026-11-16T00:00:00Z'));
    expect(d.capital).toBe(10_000);
    expect(d.start.getUTCFullYear()).toBe(2024);
    const c = handoffConfig('s1', 1, undefined);
    expect(c.benchmarkSymbol).toBe('SPY');
  });
});

describe('changedHunk', () => {
  it('keeps changed lines with one line of context', () => {
    const lines = changedHunk(diffCode('a\nb\nc\nd\ne', 'a\nb\nX\nd\ne'));
    expect(lines.map((l) => `${l.kind}:${l.text}`)).toEqual(['same:b', 'del:c', 'add:X', 'same:d']);
  });

  it('is empty when nothing changed', () => {
    expect(changedHunk(diffCode('a\nb', 'a\nb'))).toEqual([]);
  });
});

describe('questionsFirstPrompt', () => {
  it('keeps the description and asks for questions first', () => {
    const p = questionsFirstPrompt('Hold bonds when RSI is high.');
    expect(p.startsWith('Hold bonds when RSI is high.')).toBe(true);
    expect(p).toContain('ask me');
  });
});
