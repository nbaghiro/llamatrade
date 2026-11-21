import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  brokerEvents,
  brokerHeadline,
  filterEvents,
  parseChecks,
  readChecks,
  recordCheck,
} from '../brokerLog';

const d = (day: number, h = 12) => new Date(Date.UTC(2026, 10, day, h));
const et = (x: Date) => `${x.getUTCHours()}:00 ET`;

describe('brokerEvents', () => {
  const events = brokerEvents(
    [
      { id: 'p', isPaper: true, apiKeyPrefix: 'PKTX4F2Q', createdAt: d(3) },
      { id: 'l', isPaper: false, apiKeyPrefix: 'AKLM9Z1R', createdAt: d(14) },
      { id: 'x', isPaper: true, apiKeyPrefix: 'PKOLD', createdAt: null },
    ],
    [
      { at: d(16), isPaper: true, valid: true },
      { at: d(17), isPaper: false, valid: false },
    ],
    [
      { id: 's1', name: 'Tech Momentum Rotation', kind: 'paper', endedAt: d(12) },
      { id: 's2', name: 'Recession Radar', kind: 'paper', endedAt: null },
    ]
  );

  it('lists connections, stopped sessions and browser checks, newest first', () => {
    expect(events.map((e) => e.text)).toEqual([
      'Live keys rejected by Alpaca',
      'Paper keys accepted by Alpaca',
      'Live account connected',
      'Tech Momentum Rotation stopped on paper',
      'Paper account connected',
    ]);
    expect(events[0]).toMatchObject({ tone: 'risk', note: 'checked from this browser' });
    expect(events[4].note).toBe('key PKTX4F2Q••••');
  });

  it('filters by account', () => {
    expect(filterEvents(events, 'live').map((e) => e.kind)).toEqual(['live', 'live']);
    expect(filterEvents(events, 'paper')).toHaveLength(3);
    expect(filterEvents(events, 'all')).toHaveLength(5);
  });
});

describe('browser checks', () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
      },
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('drops anything malformed', () => {
    expect(parseChecks(null)).toEqual([]);
    expect(parseChecks('not json')).toEqual([]);
    expect(parseChecks('{"a":1}')).toEqual([]);
    expect(
      parseChecks(
        JSON.stringify([
          { at: 'nope', isPaper: true, valid: true },
          { at: '2026-11-16T15:00:00.000Z', isPaper: 'yes', valid: true },
          { at: '2026-11-16T15:00:00.000Z', isPaper: true, valid: false },
        ])
      )
    ).toEqual([{ at: new Date('2026-11-16T15:00:00.000Z'), isPaper: true, valid: false }]);
  });

  it('keeps the newest fifty on this device', () => {
    for (let i = 0; i < 55; i++) recordCheck({ at: d(1, i % 24), isPaper: true, valid: true });
    recordCheck({ at: d(18), isPaper: false, valid: true });
    const kept = readChecks();
    expect(kept).toHaveLength(50);
    expect(kept[0]).toEqual({ at: d(18), isPaper: false, valid: true });
  });
});

describe('brokerHeadline', () => {
  it('says what is connected and when this browser last checked', () => {
    expect(brokerHeadline(['live', 'paper'], 0, d(18, 15), et)).toBe(
      'Both accounts connected. Last checked from this browser at 15:00 ET.'
    );
    expect(brokerHeadline(['paper'], 0, null, et)).toBe(
      'Paper account connected. Not checked from this browser yet.'
    );
    expect(brokerHeadline(['paper'], 1, null, et)).toBe(
      'One account needs a look. Not checked from this browser yet.'
    );
    expect(brokerHeadline([], 0, null, et)).toBe('No Alpaca account connected.');
  });
});
