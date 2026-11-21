import {
  ACCOUNT,
  BACKTESTS,
  SAMPLE_ACCOUNT_INDEX,
  SAMPLE_FUND_RETURNS,
  SAMPLE_SESSION_VALUES,
  SAMPLE_SPY_CLOSES,
  SESSIONS,
  series,
  STRATEGIES,
  type Backtest,
  type Rule,
  type Session,
  type Strategy,
} from '../data';

export const DAY = 86_400_000;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const dayLabel = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;
export const monthLabel = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
export const fullDay = (d: Date) =>
  `${MON[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
export const iso = (s: string) => new Date(`${s}T00:00:00Z`);

export const TODAY = iso('2026-11-20');

export const tone = (v: number) => (v > 0 ? 'text-gain' : v < 0 ? 'text-loss' : 'text-fg-2');
export const pts = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`;
export const pts2 = (v: number, d = 2) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}%`;
export const money0 = (v: number) =>
  `${v < 0 ? '−' : ''}$${Math.round(Math.abs(v)).toLocaleString('en-US')}`;

function rng(seed: number) {
  let s = seed * 7919 + 13;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

export function weekdays(from: Date, to: Date): Date[] {
  const out: Date[] = [];
  for (let t = from.getTime(); t <= to.getTime(); t += DAY) {
    const d = new Date(t);
    const w = d.getUTCDay();
    if (w !== 0 && w !== 6) out.push(d);
  }
  return out;
}

function interp(anchors: [string, number][], dates: Date[]): number[] {
  const a = anchors.map(([d, v]) => [iso(d).getTime(), v] as const);
  return dates.map((d) => {
    const t = d.getTime();
    if (t <= a[0][0]) return a[0][1];
    for (let i = 1; i < a.length; i++) {
      if (t <= a[i][0]) {
        const k = (t - a[i - 1][0]) / (a[i][0] - a[i - 1][0]);
        return a[i - 1][1] + (a[i][1] - a[i - 1][1]) * k;
      }
    }
    return a[a.length - 1][1];
  });
}

/** A random walk pinned to zero at both ends, so the anchors still meet their figures. */
function wiggle(seed: number, n: number, amp: number): number[] {
  const r = rng(seed);
  const raw = [0];
  for (let i = 1; i < n; i++) raw.push(raw[i - 1] * 0.92 + (r() - 0.5) * amp);
  const end = raw[n - 1];
  return raw.map((v, i) => v - (end * i) / Math.max(1, n - 1));
}

/* ---------- Account against SPY ---------- */

export type Range = '1M' | '3M' | 'YTD' | '1Y';
export const RANGES: Range[] = ['1M', '3M', 'YTD', '1Y'];
export const RANGE_WORDS: Record<Range, string> = {
  '1M': 'Past month',
  '3M': 'Past three months',
  YTD: 'This year',
  '1Y': 'Past year',
};

export const ALL_DATES = weekdays(iso('2025-11-20'), TODAY);
const ACC_ANCHORS: [string, number][] = [
  ...SAMPLE_ACCOUNT_INDEX,
  ['2026-11-19', 111.39],
  ['2026-11-20', 111.39 * (1 + ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today))],
];
const SPY_ANCHORS: [string, number][] = [
  ...SAMPLE_SPY_CLOSES,
  ['2026-11-19', 715.85],
  ['2026-11-20', 702.96],
];
const accIdx = (() => {
  const base = interp(ACC_ANCHORS, ALL_DATES);
  const w = wiggle(5, base.length, 1.1);
  return base.map((v, i) => v + w[i]);
})();
const spyPx = (() => {
  const base = interp(SPY_ANCHORS, ALL_DATES);
  const w = wiggle(9, base.length, 9);
  return base.map((v, i) => v + w[i]);
})();

export interface Marker {
  date: Date;
  label: string;
}

export const ACCOUNT_EVENTS: Marker[] = [
  { date: iso('2026-08-04'), label: 'All-Weather started on live' },
  { date: iso('2026-10-08'), label: 'Tech Momentum started on paper' },
  { date: iso('2026-11-04'), label: 'Recession Radar started on paper' },
  { date: iso('2026-11-09'), label: 'Momentum Sectors started on paper' },
  { date: iso('2026-11-12'), label: 'Tech Momentum stopped' },
];

export interface Window {
  dates: Date[];
  main: number[];
  bench: number[];
  markers: { i: number; n: number; label: string }[];
}

export const toPct = (v: number[]) => v.map((x) => (x / v[0] - 1) * 100);

export function nearest(dates: Date[], d: Date) {
  let best = 0;
  dates.forEach((x, i) => {
    if (Math.abs(x.getTime() - d.getTime()) < Math.abs(dates[best].getTime() - d.getTime()))
      best = i;
  });
  return best;
}

function markersIn(dates: Date[], events: Marker[]) {
  const first = dates[0].getTime();
  const last = dates[dates.length - 1].getTime();
  return events
    .filter((e) => e.date.getTime() >= first && e.date.getTime() <= last)
    .map((e, k) => ({ i: nearest(dates, e.date), n: k + 1, label: e.label }));
}

export function rangeStart(range: Range): number {
  const n = ALL_DATES.length;
  return range === '1M'
    ? n - 22
    : range === '3M'
      ? n - 64
      : range === 'YTD'
        ? ALL_DATES.findIndex((d) => d.getUTCFullYear() === 2026)
        : 0;
}

export function accountWindow(range: Range): Window {
  const start = rangeStart(range);
  const dates = ALL_DATES.slice(start);
  return {
    dates,
    main: toPct(accIdx.slice(start)),
    bench: toPct(spyPx.slice(start)),
    markers: markersIn(dates, ACCOUNT_EVENTS),
  };
}

export function drawdown(v: number[]): number[] {
  let peak = -Infinity;
  return v.map((x) => {
    const g = 100 + x;
    peak = Math.max(peak, g);
    return (g / peak - 1) * 100;
  });
}

/* ---------- Strategies, sessions and backtests ---------- */

export const lastBacktest = (id: string): Backtest | undefined =>
  BACKTESTS.find((b) => b.strategyId === id);

export const activeSession = (id: string): Session | undefined =>
  SESSIONS.find((s) => s.strategyId === id && !s.stoppedOn);

export const latestSession = (id: string): Session | undefined =>
  SESSIONS.find((s) => s.strategyId === id);

export function backtestWindow(b: Backtest): Window {
  const main = series(b.seed, b.ret, 104);
  const bench = series(3, b.spy, 104);
  const endT = TODAY.getTime();
  const dates = main.map((_, i) => new Date(endT - (103 - i) * 7 * DAY));
  return { dates, main: toPct(main), bench: toPct(bench), markers: [] };
}

export function sessionWindow(s: Session): Window {
  const anchors = SAMPLE_SESSION_VALUES[s.id] ?? [];
  const end = s.stoppedOn ? iso('2026-11-12') : TODAY;
  const all: [string, number][] = s.stoppedOn
    ? [...anchors, ['2026-11-12', s.value]]
    : [...anchors, ['2026-11-19', s.value - s.today], ['2026-11-20', s.value]];
  const dates = weekdays(iso(all[0][0]), end);
  const base = interp(all, dates);
  const w = wiggle(Math.round(s.value) % 97, base.length, base[0] * 0.006);
  const vals = base.map((v, i) => v + w[i]);
  const sw = wiggle(9, dates.length, 6);
  const spy = interp(SPY_ANCHORS, dates).map((v, i) => v + sw[i]);
  return {
    dates,
    main: toPct(vals),
    bench: toPct(spy),
    markers: [],
  };
}

export const sessionValues = (s: Session) => {
  const w = sessionWindow(s);
  const first = SAMPLE_SESSION_VALUES[s.id]?.[0]?.[1] ?? s.value;
  return { w, first, since: s.value / first - 1 };
};

export function strategySpark(st: Strategy): number[] | null {
  const ses = activeSession(st.id);
  if (ses) return sessionWindow(ses).main;
  const b = lastBacktest(st.id);
  return b ? series(b.seed, b.ret, 52) : null;
}

export const RUNNING = STRATEGIES.filter((s) => s.state === 'running');
export const RESTING = STRATEGIES.filter((s) => s.state !== 'running');

/* ---------- Funds and asset classes ---------- */

export const FUND_NAME: Record<string, string> = {
  VGLT: 'Long Treasuries',
  TLT: 'Long Treasuries',
  IEF: '7–10y Treasuries',
  VTI: 'US total market',
  XLC: 'Communication',
  XLF: 'Financials',
  XLI: 'Industrials',
  XLK: 'Technology',
  GLD: 'Gold',
  DBC: 'Commodities',
  SPY: 'S&P 500',
  QQQ: 'Nasdaq 100',
  SMH: 'Semiconductors',
  VXUS: 'International stocks',
  BIL: '1 to 3 month T-bills',
  BND: 'US bonds',
};

export const FUND_CLASS: Record<string, string> = {
  VGLT: 'Long-term Treasuries',
  TLT: 'Long-term Treasuries',
  IEF: 'Intermediate Treasuries',
  VTI: 'US stocks',
  XLC: 'US sectors',
  XLF: 'US sectors',
  XLI: 'US sectors',
  GLD: 'Gold',
  DBC: 'Commodities',
};

/** Today's change per fund, in percent. Sample, for the playground. */
export const FUND_TODAY: Record<string, number> = {
  VGLT: -0.31,
  TLT: -0.42,
  IEF: -0.12,
  VTI: -1.71,
  XLC: -1.12,
  XLF: -0.88,
  XLI: -0.95,
  GLD: -0.64,
  DBC: -0.21,
};

export interface Holding {
  symbol: string;
  value: number;
  live: number;
  paper: number;
  sessions: string[];
}

export const HOLDINGS: Holding[] = (() => {
  const map = new Map<string, Holding>();
  for (const s of SESSIONS) {
    if (s.stoppedOn) continue;
    for (const h of s.holds) {
      const v = (s.value * h.weight) / 100;
      const cur = map.get(h.symbol) ?? {
        symbol: h.symbol,
        value: 0,
        live: 0,
        paper: 0,
        sessions: [],
      };
      cur.value += v;
      if (s.mode === 'live') cur.live += v;
      else cur.paper += v;
      cur.sessions.push(s.strategyId);
      map.set(h.symbol, cur);
    }
  }
  return [...map.values()].sort((a, b) => b.value - a.value);
})();

export const CASH = ACCOUNT.total - HOLDINGS.reduce((a, h) => a + h.value, 0);

export interface AssetClass {
  name: string;
  value: number;
  symbols: string[];
  today: number;
}

export const ASSET_CLASSES: AssetClass[] = (() => {
  const map = new Map<string, AssetClass>();
  for (const h of HOLDINGS) {
    const name = FUND_CLASS[h.symbol] ?? 'Other';
    const cur = map.get(name) ?? { name, value: 0, symbols: [], today: 0 };
    cur.value += h.value;
    cur.today += (h.value * (FUND_TODAY[h.symbol] ?? 0)) / 100;
    cur.symbols.push(h.symbol);
    map.set(name, cur);
  }
  const out = [...map.values()].sort((a, b) => b.value - a.value);
  out.push({ name: 'Cash', value: CASH, symbols: [], today: 0 });
  return out;
})();

export const fundSpark = (symbol: string) => {
  const r = SAMPLE_FUND_RETURNS[symbol]?.['1Y'] ?? 0;
  const seed = [...symbol].reduce((a, c) => a + c.charCodeAt(0), 0);
  return series(seed, r / 100, 52);
};

/* ---------- Copilot proposals ---------- */

export interface Proposal {
  version: number;
  note: string;
  rules: Rule[];
  effect: { ret: number; worst: number };
}

const sym = (text: string) => ({ kind: 'symbol' as const, text });
const num = (text: string) => ({ kind: 'number' as const, text });

export const PROPOSALS: Record<string, Proposal> = {
  'recession-radar': {
    version: 4,
    note: 'Gold from 40% to 30%, IEF added at 10%',
    effect: { ret: 0.209, worst: -0.126 },
    rules: [
      {
        parts: ['If', sym('SPY'), 'closes below its', num('200-day'), 'average'],
        group: 'Defensive',
        funds: [
          { symbol: 'TLT', weight: '60%' },
          { symbol: 'GLD', weight: '30%' },
          { symbol: 'IEF', weight: '10%' },
        ],
      },
      { parts: ['Otherwise hold', sym('SPY')], funds: [{ symbol: 'SPY', weight: '100%' }] },
    ],
  },
  'momentum-sectors': {
    version: 6,
    note: 'Top 4 sector funds instead of top 3',
    effect: { ret: 0.162, worst: -0.149 },
    rules: [
      {
        parts: [
          'Pick the',
          { kind: 'word', text: 'top' },
          num('4'),
          'sector funds by',
          { kind: 'word', text: 'momentum' },
          'over',
          num('90 days'),
        ],
        children: [{ parts: ['Hold them at', { kind: 'word', text: 'equal weight' }] }],
        funds: [
          { symbol: 'XLC', weight: '25%' },
          { symbol: 'XLF', weight: '25%' },
          { symbol: 'XLI', weight: '25%' },
          { symbol: 'XLK', weight: '25%' },
        ],
      },
    ],
  },
};

/** Activity of a session, newest first. Sample, for the playground. */
export function sessionActivity(s: Session): { when: string; what: string; detail: string }[] {
  if (s.id === 's-rr')
    return [
      { when: 'Nov 13', what: 'Rebalanced', detail: 'SPY closed under its 200-day average' },
      { when: 'Nov 13', what: 'Sold SPY', detail: '44.6 shares at $704.85' },
      { when: 'Nov 13', what: 'Bought TLT, GLD', detail: '60% and 40% of the session' },
      { when: 'Nov 4', what: 'Started on paper', detail: 'Version 3, $31,200' },
    ];
  if (s.id === 's-ms')
    return [
      { when: 'Nov 16', what: 'Rebalanced', detail: 'Same three funds, weights reset' },
      { when: 'Nov 9', what: 'Bought XLC, XLF, XLI', detail: 'Equal weight' },
      { when: 'Nov 9', what: 'Started on paper', detail: 'Version 5, $21,500' },
    ];
  if (s.id === 's-tm')
    return [
      { when: 'Nov 12', what: 'Stopped', detail: 'Positions closed, $26,198.65 in cash' },
      { when: 'Oct 20', what: 'Rebalanced', detail: 'Held SMH' },
      { when: 'Oct 8', what: 'Started on paper', detail: 'Version 4, $25,000' },
    ];
  return [
    { when: 'Nov 3', what: 'Rebalanced', detail: 'Back to target weights, 5 orders' },
    { when: 'Oct 1', what: 'Rebalanced', detail: 'Back to target weights, 4 orders' },
    { when: 'Aug 4', what: 'Started on live', detail: 'Version 2, $46,000' },
  ];
}
