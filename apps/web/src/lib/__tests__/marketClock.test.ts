import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';
import { describe, expect, it } from 'vitest';

import {
  asOfCloseLabel,
  barClock,
  derivedNextOpen,
  describeOpen,
  etClock,
  etParts,
  etToDate,
  isSessionOpen,
  marketChip,
} from '../marketClock';

// Nov 13 2026 is a Friday; New York is on EST (UTC-5).
const et = (day: number, h: number, m = 0) => etToDate(2026, 10, day, h * 60 + m);

describe('etToDate', () => {
  it('maps New York wall time to the right instant in winter and summer', () => {
    expect(etToDate(2026, 10, 13, 9 * 60 + 30).toISOString()).toBe('2026-11-13T14:30:00.000Z');
    expect(etToDate(2026, 6, 1, 9 * 60 + 30).toISOString()).toBe('2026-07-01T13:30:00.000Z');
  });

  it('rolls day overflow into the next month', () => {
    const p = etParts(etToDate(2026, 10, 31, 600));
    expect([p.month, p.day]).toEqual([11, 1]);
  });
});

describe('isSessionOpen', () => {
  it('is open from 9:30 to 16:00 on weekdays', () => {
    expect(isSessionOpen(et(13, 9, 29))).toBe(false);
    expect(isSessionOpen(et(13, 9, 30))).toBe(true);
    expect(isSessionOpen(et(13, 15, 59))).toBe(true);
    expect(isSessionOpen(et(13, 16, 0))).toBe(false);
    expect(isSessionOpen(et(14, 11))).toBe(false);
  });
});

describe('derivedNextOpen', () => {
  it('is later today before the open', () => {
    expect(derivedNextOpen(et(13, 8)).toISOString()).toBe(et(13, 9, 30).toISOString());
  });

  it('skips the weekend after Friday', () => {
    expect(derivedNextOpen(et(13, 17)).toISOString()).toBe(et(16, 9, 30).toISOString());
    expect(derivedNextOpen(et(14, 12)).toISOString()).toBe(et(16, 9, 30).toISOString());
  });

  it('is tomorrow after a midweek close', () => {
    expect(derivedNextOpen(et(11, 16, 30)).toISOString()).toBe(et(12, 9, 30).toISOString());
  });
});

describe('describeOpen', () => {
  it('omits the day for later today', () => {
    expect(describeOpen(et(13, 9, 30), et(13, 7))).toBe('9:30 ET');
  });

  it('names the day otherwise', () => {
    expect(describeOpen(et(16, 9, 30), et(14, 12))).toBe('Mon 9:30 ET');
  });
});

describe('marketChip', () => {
  it('shows the time while open', () => {
    expect(
      marketChip({ status: MarketStatus.OPEN, source: 'rpc', nextOpen: null, now: et(13, 10, 42) })
    ).toEqual({
      open: true,
      text: 'Market open · 10:42 ET',
    });
  });

  it('says when it opens while closed, using the service time', () => {
    expect(
      marketChip({
        status: MarketStatus.CLOSED,
        source: 'rpc',
        nextOpen: et(16, 9, 30),
        now: et(14, 13),
      })
    ).toEqual({ open: false, text: 'Market closed · opens Mon 9:30 ET' });
  });

  it('names pre-market and after hours', () => {
    expect(
      marketChip({
        status: MarketStatus.PRE_MARKET,
        source: 'rpc',
        nextOpen: et(13, 9, 30),
        now: et(13, 7),
      }).text
    ).toBe('Pre-market · opens 9:30 ET');
    expect(
      marketChip({
        status: MarketStatus.AFTER_HOURS,
        source: 'rpc',
        nextOpen: et(16, 9, 30),
        now: et(13, 17),
      }).text
    ).toBe('After hours · opens Mon 9:30 ET');
  });

  it('falls back to the wall clock without a service answer', () => {
    expect(
      marketChip({ status: null, source: 'derived', nextOpen: null, now: et(14, 12) }).text
    ).toBe('Market closed · opens Mon 9:30 ET');
    expect(
      marketChip({
        status: MarketStatus.UNSPECIFIED,
        source: 'rpc',
        nextOpen: null,
        now: et(13, 11),
      }).open
    ).toBe(true);
  });
});

describe('asOfCloseLabel', () => {
  it("uses the previous close before today's close", () => {
    expect(asOfCloseLabel(et(13, 12))).toBe('As of Thu, Nov 12 close');
  });

  it('uses today after the close', () => {
    expect(asOfCloseLabel(et(13, 16, 5))).toBe('As of Fri, Nov 13 close');
  });

  it('uses Friday over the weekend and on Monday morning', () => {
    expect(asOfCloseLabel(et(14, 12))).toBe('As of Fri, Nov 13 close');
    expect(asOfCloseLabel(et(15, 23))).toBe('As of Fri, Nov 13 close');
    expect(asOfCloseLabel(et(16, 8))).toBe('As of Fri, Nov 13 close');
  });

  it('crosses a month boundary', () => {
    expect(asOfCloseLabel(etToDate(2026, 11, 1, 600))).toBe('As of Mon, Nov 30 close');
  });
});

describe('barClock', () => {
  it('gives the New York time and the state', () => {
    expect(
      barClock({ status: MarketStatus.OPEN, source: 'rpc', nextOpen: null, now: et(13, 10, 42) })
    ).toMatchObject({ open: true, time: '10:42 ET', state: 'open' });
    expect(
      barClock({
        status: MarketStatus.AFTER_HOURS,
        source: 'rpc',
        nextOpen: et(16, 9, 30),
        now: et(13, 17, 5),
      })
    ).toMatchObject({ open: false, time: '17:05 ET', state: 'after hours' });
    expect(
      barClock({ status: null, source: 'derived', nextOpen: null, now: et(14, 12) })
    ).toMatchObject({ open: false, state: 'closed', detail: 'Market closed · opens Mon 9:30 ET' });
  });

  it('formats a bare ET clock', () => {
    expect(etClock(et(13, 9, 5))).toBe('9:05');
  });
});
