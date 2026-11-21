import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { sessionStateView, type SessionState } from '../../../lib/sessionState';
import { accountRows } from '../accountRows';
import { AccountTree } from '../AccountTree';
import { movedSummary, nextEntries } from '../dayModel';
import { ComingNext, MovedToday } from '../DayPanels';
import { HomeHead, NoHistory, type HeroFigures } from '../HomeHead';
import type { Fill, HomeSession, MarketPhase, ScheduleRow } from '../homeModel';
import { PerfCard } from '../PerfCard';
import { perfWindow } from '../perfModel';

const html = (node: JSX.Element) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

function session(over: Partial<HomeSession> = {}): HomeSession {
  const state: SessionState = over.state ?? 'running';
  return {
    id: 's1',
    name: 'Recession Radar',
    mode: 'paper',
    state,
    view: sessionStateView(state),
    rebalance: 'Monthly',
    value: 31904.2,
    today: 196.62,
    todayPct: 0.0062,
    startedAt: new Date('2026-08-01T14:00:00Z'),
    stoppedAt: null,
    frozenAt: null,
    equity: [],
    curve: [],
    allocated: 30000,
    href: '/trading/s1',
    ...over,
  };
}

const fill: Fill = {
  id: 'f1',
  sessionId: 's1',
  symbol: 'TLT',
  side: 'buy',
  quantity: 42,
  price: 90.41,
  amount: 3797.22,
  at: new Date('2026-11-17T15:31:00Z'),
};

const open: MarketPhase = {
  open: true,
  close: new Date('2026-11-17T21:00:00Z'),
  nextOpen: null,
  closeClock: '16:00',
};

const figures: HeroFigures = {
  kinds: 'paper and live',
  total: 128406.12,
  today: 612.4,
  todayPct: 0.0048,
  cash: 31820.15,
  live: 48210.55,
  paper: 80195.57,
  showSplit: true,
  staleSince: null,
  onRetry: () => undefined,
  retrying: false,
};

const head = (over: Partial<Parameters<typeof HomeHead>[0]> = {}) =>
  html(
    <HomeHead
      figures={figures}
      date="Tuesday, November 17"
      sub="2 sessions running · nothing needs you"
      spy={{ value: -0.018, when: 'today' }}
      open
      {...over}
    />
  );

describe('Home head', () => {
  it('shows the total, today, SPY and the live and paper split', () => {
    const out = head();
    expect(out).toContain('$128,406.12');
    expect(out).toContain('+$612.40 (+0.48%)');
    expect(out).toContain('−1.80%');
    expect(out).toContain('Live');
    expect(out).toContain('$48,210.55');
    expect(out).toContain('Paper and live on Alpaca');
    expect(out).not.toContain('Ask Copilot');
  });

  it('says the figures are at the close while the market is closed', () => {
    const out = head({ open: false, spy: { value: 0.0042, when: 'on Friday' } });
    expect(out).toContain('At the close, paper and live');
    expect(out).toContain('+0.42%');
    expect(out).toContain('on Friday');
  });

  it('keeps a figure that could not refresh, with its time', () => {
    const out = head({ figures: { ...figures, staleSince: new Date('2026-11-17T15:31:00Z') } });
    expect(out).toContain('From 10:31. Couldn&#x27;t refresh.');
    expect(out).toContain('Try again');
  });

  it('shows what failed in place of the figures', () => {
    const out = head({ failed: <p>Account figures couldn&apos;t be loaded.</p> });
    expect(out).not.toContain('$128,406.12');
    expect(out).toContain('Account figures couldn&#x27;t be loaded.');
  });
});

describe('Account against SPY', () => {
  const days = ['2026-11-12', '2026-11-13', '2026-11-16', '2026-11-17'].map(
    (d) => new Date(`${d}T21:00:00Z`)
  );
  const end = new Date('2026-11-17T21:30:00Z');

  it('shows the empty state without two snapshots', () => {
    const out = html(
      <PerfCard
        perf={null}
        range="1M"
        onRange={() => undefined}
        selection={null}
        hotSession={null}
        empty={<NoHistory />}
      />
    );
    expect(out).toContain('No daily history yet');
  });

  it('draws the stats, the session changes and the drawdown', () => {
    const perf = perfWindow(
      { dates: days, values: [100, 102, 99, 101] },
      days.map((d, i) => ({ timestamp: d.toISOString(), value: [0, 1, 2, 1][i] })),
      [session({ startedAt: new Date('2026-11-13T15:00:00Z') })],
      [fill],
      '1M',
      end
    );
    const out = html(
      <PerfCard
        perf={perf}
        range="1M"
        onRange={() => undefined}
        selection={null}
        hotSession={null}
        empty={<NoHistory />}
      />
    );
    expect(out).toContain('+1.00%');
    expect(out).toContain('Recession Radar started');
    expect(out).toContain('Drawdown from the range');
    expect(out).toContain('Reached Nov 16');
  });
});

describe('Your account', () => {
  it('nests sessions under their mode with figures, and marks a frozen session', () => {
    const rows = accountRows({
      sessions: [session(), session({ id: 's2', name: 'Momentum', state: 'frozen' })],
      sources: new Map(),
      total: 70000,
      today: 400,
      day: new Date('2026-11-17T00:00:00Z'),
    });
    const out = html(
      <AccountTree
        rows={rows}
        months={new Map()}
        hover={null}
        pin={null}
        hotSession={null}
        onHover={() => undefined}
        onPin={() => undefined}
      />
    );
    expect(out).toContain('All accounts');
    expect(out).toContain('Paper account');
    expect(out).toContain('Recession Radar');
    expect(out).toContain('$31,904.20');
    expect(out).toContain('Waiting for your review');
    expect(out).toContain('Not in a session');
  });
});

describe('What moved and what comes next', () => {
  it('compares each session with SPY and sums the day', () => {
    const out = html(
      <MovedToday
        sessions={[session(), session({ id: 'x', name: 'Tech', state: 'stopped' })]}
        today={612.4}
        todayPct={0.0048}
        spy={-0.018}
        phase={open}
        when="today"
        hotSession={null}
        onHover={() => undefined}
      />
    );
    expect(out).toContain('What moved today');
    expect(out).toContain('Recession Radar');
    expect(out).not.toContain('Tech');
    expect(out).toContain('SPY −1.80%');
    expect(out).toContain('One running session has moved');
  });

  it('titles the recap after the close and explains an empty day', () => {
    const out = html(
      <MovedToday
        sessions={[session({ today: null, todayPct: null })]}
        today={null}
        todayPct={null}
        spy={null}
        phase={{ ...open, open: false }}
        when="on Friday"
        hotSession={null}
        onHover={() => undefined}
      />
    );
    expect(out).toContain('How the day closed');
    expect(out).toContain('No running session has a figure for on Friday yet.');
  });

  it('summarises several sessions in one sentence', () => {
    expect(movedSummary([{ usd: -190 }, { usd: -207 }], -0.018, true)).toBe(
      'Both running sessions moved between −$207.00 and −$190.00, while SPY moved −1.80%.'
    );
  });

  it('lists the open, holidays and frozen waits in order', () => {
    const rows: ScheduleRow[] = [
      { day: new Date('2026-11-26T00:00:00Z'), kind: 'closed', sessions: [], name: 'Thanksgiving' },
      {
        day: new Date('2026-11-30T00:00:00Z'),
        kind: 'rebalance',
        sessions: [session({ state: 'frozen' })],
        name: null,
      },
    ];
    const today = new Date('2026-11-17T00:00:00Z');
    const entries = nextEntries(
      rows,
      [],
      { ...open, open: false, nextOpen: new Date('2026-11-18T14:30:00Z') },
      today
    );
    expect(entries.map((e) => e.title)).toEqual([
      'The market opens',
      'The market is closed',
      'Recession Radar rebalances',
    ]);
    const out = html(
      <ComingNext entries={entries} today={today} hotSession={null} onHover={() => undefined} />
    );
    expect(out).toContain('Closed for Thanksgiving.');
    expect(out).toContain('Recession Radar waits until the difference with Alpaca is reviewed.');
    expect(out).toContain('Market closed Nov 26');
  });

  it('puts today’s rebalances first while the market is open', () => {
    const entries = nextEntries([], [session()], open, new Date('2026-11-17T00:00:00Z'));
    expect(entries[0].title).toBe('Recession Radar rebalances');
    expect(entries[0].detail).toBe('Before the close at 16:00 ET.');
  });
});
