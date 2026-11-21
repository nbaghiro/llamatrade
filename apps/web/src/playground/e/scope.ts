import {
  ACCOUNT,
  SAMPLE_FUND_RETURNS,
  series,
  SESSIONS,
  strategyById,
  type Backtest,
  type Session,
} from '../data';

import {
  accountWindow,
  ALL_DATES,
  backtestWindow,
  drawdown,
  FUND_NAME,
  pts,
  rangeStart,
  sessionValues,
  sessionWindow,
  type Range,
  type Window,
} from './model';

export interface ScopeFigure {
  label: string;
  value: string;
  sub?: string;
  tone?: number;
}

/** What the chart and the Ask line are about: the row selected in the tree. */
export interface Scope {
  key: string;
  path: string[];
  title: string;
  value?: number;
  today?: number;
  /** A note under the big figure, e.g. "Live $48,413.97 · Paper $84,982.99". */
  note?: string;
  mainLabel: string;
  ranged: boolean;
  window: (range: Range) => Window;
  figures: (w: Window) => ScopeFigure[];
  ask: { context?: string; placeholder: string; suggestions?: string[] };
}

const rebase = (v: number[]) => v.map((x) => ((1 + x / 100) / (1 + v[0] / 100) - 1) * 100);

/** Keeps the part of a window inside the range, rebased to its first point. */
export function sliceWindow(w: Window, range: Range): Window {
  const from = ALL_DATES[rangeStart(range)].getTime();
  const i = Math.max(
    0,
    w.dates.findIndex((d) => d.getTime() >= from)
  );
  if (i === 0) return w;
  return {
    dates: w.dates.slice(i),
    main: rebase(w.main.slice(i)),
    bench: rebase(w.bench.slice(i)),
    markers: w.markers.filter((m) => m.i >= i).map((m) => ({ ...m, i: m.i - i })),
  };
}

const seedOf = (symbol: string) => [...symbol].reduce((a, c) => a + c.charCodeAt(0), 0);

const fundPath = (symbol: string) =>
  series(seedOf(symbol), (SAMPLE_FUND_RETURNS[symbol]?.['1Y'] ?? 8) / 100, ALL_DATES.length);

/** A weighted mix of funds against SPY over the range. */
export function fundsWindow(parts: { symbol: string; weight: number }[], range: Range): Window {
  const acc = accountWindow(range);
  const start = rangeStart(range);
  const total = parts.reduce((a, p) => a + p.weight, 0) || 1;
  const paths = parts.map((p) => {
    const raw = fundPath(p.symbol).slice(start);
    return { k: p.weight / total, pct: raw.map((x) => (x / raw[0] - 1) * 100) };
  });
  const main = acc.dates.map((_, i) => paths.reduce((a, p) => a + p.k * p.pct[i], 0));
  return { dates: acc.dates, main, bench: acc.bench, markers: [] };
}

const last = (v: number[]) => v[v.length - 1];

export function rangeFigures(w: Window): ScopeFigure[] {
  const ret = last(w.main);
  const spy = last(w.bench);
  return [
    { label: 'Return', value: pts(ret), sub: `SPY ${pts(spy)}`, tone: ret },
    {
      label: 'Against SPY',
      value: `${ret - spy >= 0 ? '+' : '−'}${Math.abs(ret - spy).toFixed(1)}`,
      sub: ret >= spy ? 'Ahead' : 'Behind',
    },
    {
      label: 'Max drop',
      value: pts(Math.min(...drawdown(w.main))),
      sub: `SPY ${pts(Math.min(...drawdown(w.bench)))}`,
    },
  ];
}

export const ACCOUNT_SCOPE: Scope = {
  key: 'account',
  path: ['Account'],
  title: 'Whole account',
  value: ACCOUNT.total,
  today: ACCOUNT.today,
  note: 'Live and paper, benchmark SPY',
  mainLabel: 'Account',
  ranged: true,
  window: accountWindow,
  figures: rangeFigures,
  ask: {
    placeholder: 'Ask about your account, or describe a strategy',
    suggestions: [
      'Why is the account down today?',
      "Lower Recession Radar's gold to 30%",
      'Draft a trend strategy on QQQ',
    ],
  },
};

const live = SESSIONS.find((s) => s.mode === 'live');

export function modeScope(mode: 'live' | 'paper'): Scope {
  const ses = SESSIONS.filter((s) => s.mode === mode);
  const today = ses.reduce((a, s) => a + s.today, 0);
  return {
    key: mode,
    path: ['Account', mode === 'live' ? 'Live' : 'Paper'],
    title: mode === 'live' ? 'Live account' : 'Paper account',
    value: mode === 'live' ? ACCOUNT.live : ACCOUNT.paper,
    today,
    note: `${ses.filter((s) => !s.stoppedOn).length} running on ${mode}`,
    mainLabel: mode === 'live' ? 'Live' : 'Paper',
    ranged: true,
    window: (r) =>
      mode === 'live' && live
        ? sliceWindow(sessionWindow(live), r)
        : (() => {
            const w = accountWindow(r);
            return { ...w, main: w.main.map((v) => v * 1.22), markers: [] };
          })(),
    figures: rangeFigures,
    ask: { placeholder: `Ask about the ${mode} account` },
  };
}

export function sessionScope(s: Session): Scope {
  const st = strategyById(s.strategyId);
  const name = st?.name ?? '';
  const { first } = sessionValues(s);
  return {
    key: s.id,
    path: ['Account', s.mode === 'live' ? 'Live' : 'Paper', name],
    title: name,
    value: s.value,
    today: s.stoppedOn ? undefined : s.today,
    note: `Version ${s.version} · started ${s.started}${s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''}`,
    mainLabel: 'Session',
    ranged: false,
    window: () => sessionWindow(s),
    figures: (w) => [
      {
        label: 'Since start',
        value: pts((s.value / first - 1) * 100),
        sub: `SPY ${pts(last(w.bench))}`,
        tone: s.value - first,
      },
      {
        label: 'Gain',
        value: `${s.value - first >= 0 ? '+' : '−'}$${Math.abs(s.value - first).toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
        sub: `from $${first.toLocaleString('en-US')}`,
      },
      {
        label: 'Holds',
        value: s.holds.length ? `${s.holds.length} funds` : 'Cash',
        sub: s.holds.map((h) => h.symbol).join(' ') || s.next,
      },
    ],
    ask: {
      context: s.strategyId,
      placeholder: `Ask about ${name}`,
      suggestions: [`Why does ${name} hold this today?`, `Suggest a safer edit to ${name}`],
    },
  };
}

export function fundScope(
  symbol: string,
  path: string[],
  value?: number,
  today?: number,
  context?: string
): Scope {
  return {
    key: `fund:${symbol}:${path.join('/')}`,
    path,
    title: `${symbol} · ${FUND_NAME[symbol] ?? ''}`,
    value,
    today,
    mainLabel: symbol,
    ranged: true,
    window: (r) => fundsWindow([{ symbol, weight: 1 }], r),
    figures: rangeFigures,
    ask: { context, placeholder: `Ask about ${symbol}` },
  };
}

export function mixScope(
  key: string,
  title: string,
  path: string[],
  parts: { symbol: string; weight: number }[],
  value?: number,
  today?: number,
  context?: string
): Scope {
  return {
    key,
    path,
    title,
    value,
    today,
    note: parts.map((p) => p.symbol).join(' '),
    mainLabel: title,
    ranged: true,
    window: (r) => fundsWindow(parts.length ? parts : [{ symbol: 'BIL', weight: 1 }], r),
    figures: rangeFigures,
    ask: { context, placeholder: `Ask about ${title}` },
  };
}

export function backtestScope(b: Backtest, path: string[]): Scope {
  const st = strategyById(b.strategyId);
  const name = st?.name ?? '';
  return {
    key: `bt:${b.id}`,
    path,
    title: `${name}, v${b.version}`,
    value: 25000 * (1 + b.ret),
    note: `Backtest · ${b.range} · from $25,000`,
    mainLabel: name,
    ranged: false,
    window: () => backtestWindow(b),
    figures: () => [
      { label: 'Return', value: pts(b.ret * 100), sub: `SPY ${pts(b.spy * 100)}`, tone: b.ret },
      { label: 'Max drop', value: pts(b.worst * 100), sub: 'SPY −20.4%' },
      { label: 'Sharpe', value: b.sharpe.toFixed(2), sub: 'SPY 0.77' },
    ],
    ask: {
      context: b.strategyId,
      placeholder: `Ask about ${name}`,
      suggestions: [`Explain ${name}`, `Suggest a safer edit to ${name}`],
    },
  };
}
