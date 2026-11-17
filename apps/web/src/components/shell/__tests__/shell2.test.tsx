import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { etToDate } from '../../../lib/marketClock';
import { dayFraction, minuteLabel, todayLanes } from '../../notifications/todayLanes';
import { OfflineBannerView } from '../../states/OfflineBanner';
import { entryArea, frozenFromSleeves, groupMarks } from '../attention';
import { BarClockView } from '../BarClock';
import { connectionRows } from '../connections';

const at = (h: number, m: number) => etToDate(2026, 10, 17, h * 60 + m);

describe('attention in the bar', () => {
  const frozen = {
    id: 'frozen-s1',
    kind: 'frozen' as const,
    title: 'Momentum Sectors is frozen.',
    detail: '',
    href: '/portfolio',
  };

  it('pins frozen and rejected work on Sessions and notices where they link', () => {
    expect(entryArea(frozen)).toBe('sessions');
    expect(entryArea({ ...frozen, kind: 'rejected' })).toBe('sessions');
    expect(entryArea({ ...frozen, kind: 'notice', href: '/backtests/r1?x=1' })).toBe('backtests');
    expect(entryArea({ ...frozen, kind: 'notice', href: '/settings/notifications' })).toBeNull();
  });

  it('groups marks by area without duplicates', () => {
    const marks = groupMarks([frozen], {
      sessionsPage: [{ id: 'frozen-s1', area: 'sessions', title: 'dup', href: '/trading' }],
      backtests: [{ id: 'b1', area: 'backtests', title: 'Failed', href: '/backtests' }],
    });
    expect(marks.sessions?.map((m) => m.title)).toEqual(['Momentum Sectors is frozen.']);
    expect(marks.backtests).toHaveLength(1);
  });

  it('reads frozen sleeves from the trading store', () => {
    expect(
      frozenFromSleeves([
        { id: 'a', name: 'A', status: SleeveStatus.FROZEN, strategyExecutionId: 'e1' },
        { id: 'b', name: 'B', status: SleeveStatus.ACTIVE, strategyExecutionId: 'e2' },
      ])
    ).toEqual([{ id: 'a', name: 'A', executionId: 'e1' }]);
  });
});

describe('connections in the account menu', () => {
  it('lists live first with what runs on each', () => {
    const rows = connectionRows(
      [
        { id: 'p', name: 'Paper', apiKeyPrefix: 'PKXXPA92', isPaper: true, isActive: true },
        { id: 'l', name: 'Live', apiKeyPrefix: 'AKXX4821', isPaper: false, isActive: false },
      ],
      [
        { mode: ExecutionMode.PAPER, isActive: true, equity: 100.5 },
        { mode: ExecutionMode.PAPER, isActive: true, equity: 50 },
        { mode: ExecutionMode.PAPER, isActive: true, equity: null },
        { mode: ExecutionMode.PAPER, isActive: false, equity: 999 },
      ]
    );
    expect(rows.map((r) => [r.mode, r.masked, r.connected, r.sessions, r.value])).toEqual([
      ['live', '••4821', false, 0, null],
      ['paper', '••PA92', true, 3, 150.5],
    ]);
  });
});

describe('today drawn as lanes', () => {
  const sessions = [
    { id: 's1', name: 'Recession Radar', isActive: true, sleeveId: 'sl1' },
    { id: 's2', name: 'Momentum Sectors', isActive: true, sleeveId: 'sl2' },
    { id: 's3', name: 'Tech Momentum', isActive: false, sleeveId: '' },
  ];

  it('groups close fills, keeps running sessions and sorts frozen first', () => {
    const lanes = todayLanes(
      sessions,
      [
        { sessionId: 's1', status: OrderStatus.FILLED, filledAt: at(10, 31) },
        { sessionId: 's1', status: OrderStatus.FILLED, filledAt: at(10, 33) },
        { sessionId: 's1', status: OrderStatus.FILLED, filledAt: at(14, 0) },
        { sessionId: 's1', status: OrderStatus.REJECTED, filledAt: at(11, 0) },
        { sessionId: 's1', status: OrderStatus.FILLED, filledAt: etToDate(2026, 10, 16, 600) },
        { sessionId: 's2', status: OrderStatus.FILLED, filledAt: at(9, 45) },
      ],
      new Set(['sl2']),
      at(15, 0)
    );
    expect(lanes.map((l) => [l.name, l.frozen])).toEqual([
      ['Momentum Sectors', true],
      ['Recession Radar', false],
    ]);
    expect(lanes[1].fills).toEqual([
      { minute: 631, count: 2 },
      { minute: 840, count: 1 },
    ]);
  });

  it('runs from the open to the close', () => {
    expect(dayFraction(9 * 60 + 30)).toBe(0);
    expect(dayFraction(16 * 60)).toBe(1);
    expect(dayFraction(20 * 60)).toBe(1);
    expect(minuteLabel(9 * 60 + 5)).toBe('9:05');
  });
});

describe('clock and offline strip', () => {
  it('stops the clock at the last update when offline', () => {
    const html = renderToStaticMarkup(
      <BarClockView time="10:38 ET" state="open" open detail="" stopped />
    );
    expect(html).toContain('10:38 ET');
    expect(html).toContain('last update');
    expect(html).not.toContain('bg-accent');
  });

  it('says trading continues, in grey', () => {
    const html = renderToStaticMarkup(
      <OfflineBannerView
        offlineSince={at(10, 38)}
        now={at(10, 40)}
        retrying={false}
        stillOffline={false}
        onRetry={() => undefined}
      />
    );
    expect(html).toContain('keep trading');
    expect(html).toContain('from 10:38 ET');
    expect(html).not.toContain('risk');
  });
});
