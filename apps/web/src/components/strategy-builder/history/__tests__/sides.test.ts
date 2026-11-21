import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { describe, expect, it } from 'vitest';

import type { TradeInput } from '../../../../lib/backtestView';
import { matchBlocks } from '../../../../lib/strategyDiff';
import { shortCondition } from '../sideHistoryView';
import {
  conditionSides,
  scheduledDates,
  sideCounts,
  sideOfBlock,
  sidesAtDates,
  sidesAtRebalances,
} from '../sides';

const d = (s: string) => new Date(`${s}T20:00:00Z`);

const trade = (symbol: string, from: string, to: string | null): TradeInput => ({
  symbol,
  side: 'BUY',
  quantity: 1,
  entryPrice: 1,
  exitPrice: 1,
  entryTime: d(from),
  exitTime: to ? d(to) : null,
  pnl: 0,
  entryReason: '',
  exitReason: '',
});

const sides = { when: new Set(['TLT', 'GLD']), otherwise: new Set(['VTI', 'QQQ']) };

// Defensive in January, stocks from February, a mixed day on Feb 10.
const trades = [
  trade('TLT', '2025-01-02', '2025-02-03'),
  trade('GLD', '2025-01-02', '2025-02-03'),
  trade('VTI', '2025-02-03', null),
  trade('QQQ', '2025-02-10', null),
  trade('GLD', '2025-02-10', '2025-02-11'),
];

describe('scheduledDates', () => {
  const days = ['2025-01-02', '2025-01-03', '2025-02-03', '2025-02-04', '2025-03-03'].map(d);
  it('takes the first trading day of each month', () => {
    expect(scheduledDates(days, 'monthly')?.map((x) => x.toISOString().slice(0, 10))).toEqual([
      '2025-01-02',
      '2025-02-03',
      '2025-03-03',
    ]);
  });
  it('is null for a daily schedule', () => {
    expect(scheduledDates(days, 'daily')).toBeNull();
  });
});

describe('sidesAtDates', () => {
  it('reads one side per scheduled rebalance and counts them', () => {
    const points = sidesAtDates(trades, [d('2025-01-02'), d('2025-02-03'), d('2025-03-03')], sides);
    expect(points.map((p) => p.side)).toEqual(['when', 'otherwise', 'otherwise']);
    expect(sideCounts(points)).toEqual({ when: 1, otherwise: 2, unknown: 0, known: 3, total: 3 });
  });

  it('counts days with orders, leaving out a mixed day', () => {
    const points = sidesAtRebalances(trades, sides);
    expect(points.map((p) => p.side)).toEqual(['when', 'otherwise', null, 'otherwise']);
    expect(sideCounts(points).unknown).toBe(1);
  });

  it('reads nothing held before the first trade as unknown', () => {
    expect(sidesAtDates(trades, [d('2024-12-02')], sides)[0].side).toBeNull();
  });
});

const SOURCE = `(strategy "R"
  :rebalance monthly
  (if (> (rsi SPY 14) 70)
    (weight :method specified
      (asset TLT :weight 60)
      (asset GLD :weight 40))
    (else
      (weight :method equal
        (asset VTI)
        (asset QQQ)))))`;

describe('sideOfBlock', () => {
  const saved = fromDSLString(SOURCE);
  const draft = fromDSLString(SOURCE.replace('70', '72'));
  if (!saved || !draft) throw new Error('fixture does not parse');
  const found = conditionSides(saved.tree);
  if (!found) throw new Error('no sides');
  const toSaved = matchBlocks(saved.tree, draft.tree);
  const byType = (type: string, symbol?: string) =>
    Object.values(draft.tree.blocks).find(
      (b) => b.type === type && (!symbol || ('symbol' in b && b.symbol === symbol))
    )?.id ?? null;

  it('maps the if, the else and blocks under them to their side', () => {
    expect(sideOfBlock(draft.tree, byType('if'), found.ifId, toSaved)).toBe('when');
    expect(sideOfBlock(draft.tree, byType('asset', 'TLT'), found.ifId, toSaved)).toBe('when');
    expect(sideOfBlock(draft.tree, byType('else'), found.ifId, toSaved)).toBe('otherwise');
    expect(sideOfBlock(draft.tree, byType('asset', 'QQQ'), found.ifId, toSaved)).toBe('otherwise');
  });

  it('is null with no selection', () => {
    expect(sideOfBlock(draft.tree, null, found.ifId, toSaved)).toBeNull();
  });

  it('shortens the condition for a lane label', () => {
    expect(shortCondition(found.condition)).toMatch(/above 70$/);
    expect(shortCondition('the 14-day RSI of SPY is above 70')).toBe('RSI above 70');
  });
});
