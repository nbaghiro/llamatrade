import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { sessionStateView, type SessionState } from '../../../lib/sessionState';
import { FirstSession } from '../FirstSession';
import { FirstVisit } from '../FirstVisit';
import { HomeHero, NoHistory, type HeroFigures } from '../HomeHero';
import type { Fill, HomeSession, MarketPhase, ScheduleRow } from '../homeModel';
import { BeforeClose, HowTodayClosed, NextList, TodayBySession, TodayFills } from '../HomePanels';

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

describe('Home panels', () => {
  it('lists today’s fills with their session and kind of money', () => {
    const out = html(
      <TodayFills
        fills={[fill]}
        sessions={[session()]}
        error={false}
        onRetry={() => undefined}
        retrying={false}
      />
    );
    expect(out).toContain('42 TLT at $90.41');
    expect(out).toContain('Recession Radar · paper');
    expect(out).toContain('1 filled');
  });

  it('fails in place when the trading service is down', () => {
    const out = html(
      <TodayFills fills={[]} sessions={[]} error onRetry={() => undefined} retrying={false} />
    );
    expect(out).toContain('Fills couldn&#x27;t be loaded');
  });

  it('says what runs before the close, and when nothing does', () => {
    expect(html(<BeforeClose due={[session()]} phase={open} />)).toContain(
      'Recession Radar rebalances today'
    );
    expect(html(<BeforeClose due={[]} phase={open} />)).toContain(
      'No rebalances are scheduled for today.'
    );
  });

  it('shows each session’s day, with stopped ones saying so', () => {
    const out = html(
      <TodayBySession
        sessions={[session(), session({ id: 'x', name: 'Tech', state: 'stopped' })]}
      />
    );
    expect(out).toContain('+$196.62');
    expect(out).toContain('Stopped');
  });

  it('recaps the closed day and lists holidays and waits after it', () => {
    const recap = html(<HowTodayClosed sessions={[session({ state: 'frozen' })]} fills={[fill]} />);
    expect(recap).toContain('Paper · frozen, prices still move');
    const rows: ScheduleRow[] = [
      { day: new Date('2026-11-26T00:00:00Z'), kind: 'closed', sessions: [], name: 'Thanksgiving' },
      {
        day: new Date('2026-11-30T00:00:00Z'),
        kind: 'rebalance',
        sessions: [session({ state: 'frozen' })],
        name: null,
      },
    ];
    const next = html(
      <NextList
        rows={rows}
        phase={{ ...open, open: false, nextOpen: new Date('2026-11-18T14:30:00Z') }}
      />
    );
    expect(next).toContain('Closed for Thanksgiving.');
    expect(next).toContain('Recession Radar waits until the difference with Alpaca is reviewed.');
    expect(next).toContain('The market opens.');
  });
});

describe('Home hero', () => {
  it('shows the total, today, the split and the empty curve state', () => {
    const out = html(
      <HomeHero
        figures={figures}
        series={{ dates: [], values: [] }}
        benchmark={[]}
        shown={[session()]}
        rest={[]}
        fills={[]}
        schedule={[]}
        phase={open}
        now={new Date('2026-11-17T15:42:00Z')}
        noHistory={<NoHistory />}
      />
    );
    expect(out).toContain('$128,406.12');
    expect(out).toContain('+$612.40');
    expect(out).toContain('Total equity');
    expect(out).toContain('paper and live');
    expect(out).toContain('No daily history yet');
  });

  it('keeps a figure that could not refresh, with its time', () => {
    const out = html(
      <HomeHero
        figures={{ ...figures, staleSince: new Date('2026-11-17T15:31:00Z') }}
        series={{ dates: [], values: [] }}
        benchmark={[]}
        shown={[]}
        rest={[]}
        fills={[]}
        schedule={[]}
        phase={open}
        now={new Date('2026-11-17T15:42:00Z')}
        noHistory={<NoHistory />}
      />
    );
    expect(out).toContain('From 10:31. Couldn&#x27;t refresh.');
    expect(out).toContain('Try again');
  });
});

describe('first visit and first session', () => {
  it('offers three ways to start', () => {
    const out = html(<FirstVisit hasStrategies={false} />);
    expect(out).toContain('Start from a template');
    expect(out).toContain('Describe it to Copilot');
    expect(out).toContain('Build from blocks');
  });

  it('spotlights the session with holdings against targets', () => {
    const out = html(
      <FirstSession
        session={session({
          startedAt: new Date('2026-11-17T15:31:00Z'),
          value: 100012.4,
          allocated: 100000,
        })}
        holdings={[{ symbol: 'VTI', shares: 137, price: 436.12, value: 59748.44, target: 0.6 }]}
        cash={255.24}
        fills={[fill, { ...fill, id: 'f2' }]}
        rejected={0}
        today={new Date('2026-11-17T00:00:00Z')}
      />
    );
    expect(out).toContain('+$12.40 since start');
    expect(out).toContain('Running since 10:31');
    expect(out).toContain('60%');
    expect(out).toContain('Rebalances on Dec 1');
    expect(out).toContain('All 2 orders so far passed every check');
  });
});
