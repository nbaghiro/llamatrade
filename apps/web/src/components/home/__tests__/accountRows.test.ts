import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { describe, expect, it } from 'vitest';

import { sessionStateView, type SessionState } from '../../../lib/sessionState';
import { accountRows, modeLine, sessionLine, type SessionSource } from '../accountRows';
import type { HomeSession } from '../homeModel';

const RADAR = `(strategy "Recession Radar"
  :rebalance monthly :benchmark SPY
  (if (< (price SPY) (sma SPY 200))
      (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
      (else (asset SPY :weight 100))))`;

function session(over: Partial<HomeSession> = {}): HomeSession {
  const state: SessionState = over.state ?? 'running';
  return {
    id: 's1',
    name: 'Recession Radar',
    mode: 'paper',
    state,
    view: sessionStateView(state),
    rebalance: 'Monthly',
    value: 1000,
    today: 12,
    todayPct: 0.012,
    startedAt: new Date('2026-11-04T15:00:00Z'),
    stoppedAt: null,
    frozenAt: null,
    equity: [],
    curve: [],
    allocated: 1000,
    href: '/trading/s1',
    ...over,
  };
}

const source = (over: Partial<SessionSource> = {}): SessionSource => ({
  strategyId: 'st1',
  version: 3,
  tree: fromDSLString(RADAR)?.tree ?? null,
  positions: [
    { symbol: 'TLT', value: 600 },
    { symbol: 'GLD', value: 390 },
  ],
  ...over,
});

const day = new Date('2026-11-17T00:00:00Z');

describe('accountRows', () => {
  it('nests account, mode and session, with shares of each parent', () => {
    const rows = accountRows({
      sessions: [session(), session({ id: 's2', name: 'Live one', mode: 'live', value: 500 })],
      sources: new Map(),
      total: 1500,
      today: 20,
      day,
    });
    expect(rows.map((r) => [r.kind, r.depth, r.label])).toEqual([
      ['account', 0, 'All accounts'],
      ['mode', 1, 'Live account'],
      ['session', 2, 'Live one'],
      ['mode', 1, 'Paper account'],
      ['session', 2, 'Recession Radar'],
    ]);
    expect(rows[1].share).toBeCloseTo(33.33, 1);
    expect(rows[2].share).toBe(100);
    expect(rows[1].lineKey).toBe(modeLine('live'));
    expect(rows[4].lineKey).toBe(sessionLine('s1'));
  });

  it('adds the strategy’s rules and holdings, marking the branch held today', () => {
    const rows = accountRows({
      sessions: [session()],
      sources: new Map([['s1', source()]]),
      total: 1000,
      today: 12,
      day,
    });
    const ifRow = rows.find((r) => r.outlineKind === 'if');
    const elseRow = rows.find((r) => r.outlineKind === 'else');
    expect(ifRow?.liveMarker).toBe(true);
    expect(elseRow?.muted).toBe(true);
    const tlt = rows.find((r) => r.symbol === 'TLT');
    expect(tlt).toMatchObject({ value: 600, share: 60, live: true, depth: 5 });
    const spy = rows.find((r) => r.symbol === 'SPY');
    expect(spy).toMatchObject({ muted: true, value: undefined });
    expect(rows.find((r) => r.kind === 'session')?.sub).toBe('v3, since Nov 4');
    expect(ifRow?.href).toBe('/strategies/st1/edit');
  });

  it('notes the next rebalance on the first top-level rule that is not a condition', () => {
    const dsl = `(strategy "Fixed" :rebalance monthly
      (weight :method equal (asset VTI) (asset BND)))`;
    const rows = accountRows({
      sessions: [session()],
      sources: new Map([['s1', source({ tree: fromDSLString(dsl)?.tree ?? null, positions: [] })]]),
      total: 1000,
      today: null,
      day,
    });
    expect(rows.find((r) => r.outlineKind === 'weight')?.note).toBe('Next rebalance Dec 1');
  });

  it('lists holdings the strategy doesn’t name, and none for a stopped session', () => {
    const rows = accountRows({
      sessions: [session(), session({ id: 's2', name: 'Old', state: 'stopped', today: null })],
      sources: new Map([
        ['s1', source({ positions: [{ symbol: 'QQQ', value: 50 }] })],
        ['s2', source()],
      ]),
      total: 2000,
      today: 12,
      day,
    });
    expect(rows.find((r) => r.symbol === 'QQQ')).toMatchObject({ depth: 3, value: 50 });
    const old = rows.find((r) => r.label === 'Old');
    expect(old).toMatchObject({ muted: true, na: 'Final value', today: undefined });
    expect(rows[rows.indexOf(old ?? rows[0]) + 1]?.sessionId).not.toBe('s2');
  });

  it('shows money outside every session and marks a frozen session', () => {
    const rows = accountRows({
      sessions: [session({ state: 'frozen', frozenAt: new Date('2026-11-16T15:00:00Z') })],
      sources: new Map(),
      total: 1200,
      today: 12,
      day,
    });
    expect(rows.find((r) => r.kind === 'session')).toMatchObject({
      warn: true,
      sub: 'frozen since Nov 16',
    });
    expect(rows.find((r) => r.id === 'outside')).toMatchObject({ value: 200 });
  });
});
