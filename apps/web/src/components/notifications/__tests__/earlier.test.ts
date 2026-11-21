import { describe, expect, it } from 'vitest';

import { collapseRepeats, plainMessage, type EarlierNotice } from '../earlier';

const ts = (iso: string) => {
  const ms = new Date(iso).getTime();
  return { seconds: BigInt(Math.floor(ms / 1000)), nanos: 0 };
};

const notice = (id: string, title: string, iso: string, isRead = true): EarlierNotice =>
  ({ id, title, message: '', isRead, createdAt: ts(iso) }) as EarlierNotice;

describe('earlier notices', () => {
  it('folds repeats of one title on one day into a row with a count', () => {
    const rows = collapseRepeats([
      notice('a', 'Broker connection lost', '2026-11-17T15:00:00Z'),
      notice('b', 'Broker connection lost', '2026-11-17T15:30:00Z', false),
      notice('c', 'Backtest finished', '2026-11-17T14:00:00Z'),
      notice('d', 'Broker connection lost', '2026-11-16T15:00:00Z'),
    ]);
    expect(rows.map((r) => [r.notice.id, r.count, r.unread])).toEqual([
      ['b', 2, true],
      ['c', 1, false],
      ['d', 1, false],
    ]);
    expect(rows[0].ids).toEqual(['a', 'b']);
  });

  it('drops internal stream ids from a message', () => {
    expect(plainMessage('A live data connection dropped: bar_stream')).toBe(
      'A live data connection dropped.'
    );
    expect(plainMessage('Bought 42 TLT: filled.')).toBe('Bought 42 TLT: filled.');
    expect(plainMessage('Done.')).toBe('Done.');
  });
});
