import type { Notification } from '@llamatrade/core/proto/notification_pb';
import { describe, expect, it } from 'vitest';

import { groupByDay } from '../groupByDay';

const n = (id: string, at: Date | null) =>
  ({
    id,
    createdAt: at ? { seconds: BigInt(Math.floor(at.getTime() / 1000)), nanos: 0 } : undefined,
  }) as unknown as Notification;

const NOW = new Date(2026, 10, 16, 10, 0);

describe('groupByDay', () => {
  it('labels today, yesterday and older days in order', () => {
    const groups = groupByDay(
      [
        n('a', new Date(2026, 10, 16, 9, 30)),
        n('b', new Date(2026, 10, 16, 0, 5)),
        n('c', new Date(2026, 10, 15, 23, 59)),
        n('d', new Date(2026, 10, 12, 8)),
      ],
      NOW
    );
    expect(groups.map((g) => [g.label, g.items.map((i) => i.id)])).toEqual([
      ['Today', ['a', 'b']],
      ['Yesterday', ['c']],
      ['Thu, Nov 12', ['d']],
    ]);
  });

  it('adds the year for an earlier year and puts undated rows under Earlier', () => {
    const groups = groupByDay([n('x', new Date(2025, 11, 31, 12)), n('y', null)], NOW);
    expect(groups.map((g) => g.label)).toEqual(['Wed, Dec 31, 2025', 'Earlier']);
  });

  it('crosses a month boundary for yesterday', () => {
    const groups = groupByDay([n('z', new Date(2026, 10, 30, 22))], new Date(2026, 11, 1, 8));
    expect(groups[0].label).toBe('Yesterday');
  });

  it('returns nothing for an empty list', () => {
    expect(groupByDay([], NOW)).toEqual([]);
  });
});
