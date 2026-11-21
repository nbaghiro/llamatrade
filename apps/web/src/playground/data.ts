/** Fixed demo data for the playground, matching the seeded demo account. Prices are Nov 20, 2026, around noon ET. */

export type Mode = 'live' | 'paper';
export type StrategyState = 'running' | 'stopped' | 'never-run' | 'draft';

export interface Value {
  kind: 'symbol' | 'number' | 'word';
  text: string;
}

/** A rule is a sentence of plain words and editable values, with optional sub-rules and fund weights. */
export interface Rule {
  parts: (string | Value)[];
  funds?: { symbol: string; weight: string; ifPicked?: boolean }[];
  children?: Rule[];
  /** A name for the funds this rule holds, kept as a `group` block in the strategy's code. */
  group?: string;
}

export interface Version {
  n: number;
  saved: string;
  note: string;
}

export interface Strategy {
  id: string;
  name: string;
  state: StrategyState;
  mode?: Mode;
  version: number;
  cadence: 'daily' | 'weekly' | 'monthly';
  summary: string;
  stoppedOn?: string;
  rules: Rule[];
  versions: Version[];
  seed: number;
}

export interface Session {
  id: string;
  strategyId: string;
  mode: Mode;
  version: number;
  value: number;
  today: number;
  started: string;
  stoppedOn?: string;
  holds: { symbol: string; weight: number }[];
  next?: string;
}

export interface Backtest {
  id: string;
  strategyId: string;
  version: number;
  ran: string;
  range: string;
  ret: number;
  spy: number;
  worst: number;
  sharpe: number;
  seed: number;
}

const sym = (text: string): Value => ({ kind: 'symbol', text });
const num = (text: string): Value => ({ kind: 'number', text });
const word = (text: string): Value => ({ kind: 'word', text });

export const ACCOUNT = {
  total: 133_396.96,
  today: -593.79,
  live: 48_413.97,
  paper: 84_982.99,
} as const;

export const MARKET = {
  status: 'Open until 16:00 ET',
  quotes: [
    { symbol: 'SPY', price: 702.96, change: -0.018 },
    { symbol: 'QQQ', price: 622.99, change: -0.0342 },
  ],
} as const;

export const STRATEGIES: Strategy[] = [
  {
    id: 'all-weather',
    name: 'All-Weather Portfolio',
    state: 'running',
    mode: 'live',
    version: 2,
    cadence: 'monthly',
    summary: 'Holds five funds in fixed weights, rebalanced monthly.',
    rules: [
      {
        parts: ['Hold', word('fixed weights'), 'and rebalance', word('monthly')],
        funds: [
          { symbol: 'VGLT', weight: '40%' },
          { symbol: 'VTI', weight: '30%' },
          { symbol: 'IEF', weight: '15%' },
          { symbol: 'GLD', weight: '7.5%' },
          { symbol: 'DBC', weight: '7.5%' },
        ],
      },
    ],
    versions: [
      { n: 2, saved: 'Aug 1', note: 'Moved 5% from IEF to VGLT' },
      { n: 1, saved: 'Jul 18', note: 'First version' },
    ],
    seed: 11,
  },
  {
    id: 'recession-radar',
    name: 'Recession Radar',
    state: 'running',
    mode: 'paper',
    version: 3,
    cadence: 'daily',
    summary: 'Moves to bonds and gold when SPY falls below its 200-day average.',
    rules: [
      {
        parts: ['If', sym('SPY'), 'closes below its', num('200-day'), 'average'],
        group: 'Defensive',
        funds: [
          { symbol: 'TLT', weight: '60%' },
          { symbol: 'GLD', weight: '40%' },
        ],
      },
      { parts: ['Otherwise hold', sym('SPY')], funds: [{ symbol: 'SPY', weight: '100%' }] },
    ],
    versions: [
      { n: 3, saved: 'Nov 4', note: 'Gold share from 30% to 40%' },
      { n: 2, saved: 'Oct 12', note: 'Average from 150 to 200 days' },
      { n: 1, saved: 'Sep 30', note: 'First version' },
    ],
    seed: 23,
  },
  {
    id: 'momentum-sectors',
    name: 'Momentum Sectors',
    state: 'running',
    mode: 'paper',
    version: 5,
    cadence: 'weekly',
    summary: 'Holds the three strongest sector funds by 90-day momentum.',
    rules: [
      {
        parts: [
          'Pick the',
          word('top'),
          num('3'),
          'sector funds by',
          word('momentum'),
          'over',
          num('90 days'),
        ],
        children: [{ parts: ['Hold them at', word('equal weight')] }],
        funds: [
          { symbol: 'XLC', weight: '33.3%' },
          { symbol: 'XLF', weight: '33.3%' },
          { symbol: 'XLI', weight: '33.3%' },
        ],
      },
    ],
    versions: [
      { n: 5, saved: 'Nov 9', note: 'Weekly instead of monthly' },
      { n: 4, saved: 'Oct 21', note: 'Top 3 instead of top 2' },
      { n: 3, saved: 'Oct 2', note: 'Added XLRE and XLC' },
    ],
    seed: 37,
  },
  {
    id: 'tech-momentum',
    name: 'Tech Momentum Rotation',
    state: 'stopped',
    mode: 'paper',
    version: 4,
    cadence: 'weekly',
    stoppedOn: 'Nov 12',
    summary: 'Rotated between QQQ, XLK and SMH by 60-day return.',
    rules: [
      {
        parts: [
          'Hold the one of',
          sym('QQQ'),
          sym('XLK'),
          sym('SMH'),
          'with the best',
          num('60-day'),
          'return',
        ],
        funds: [
          { symbol: 'QQQ', weight: '100%', ifPicked: true },
          { symbol: 'XLK', weight: '100%', ifPicked: true },
          { symbol: 'SMH', weight: '100%', ifPicked: true },
        ],
      },
    ],
    versions: [
      { n: 4, saved: 'Oct 7', note: 'Lookback from 90 to 60 days' },
      { n: 3, saved: 'Sep 19', note: 'Added SMH' },
    ],
    seed: 41,
  },
  {
    id: 'dual-momentum',
    name: 'Dual Momentum',
    state: 'never-run',
    version: 1,
    cadence: 'monthly',
    summary: 'US or international stocks by 12-month return, bonds when both trail cash.',
    rules: [
      {
        parts: [
          'If',
          sym('VTI'),
          'and',
          sym('VXUS'),
          'both trail',
          sym('BIL'),
          'over',
          num('12 months'),
        ],
        funds: [{ symbol: 'BND', weight: '100%' }],
      },
      {
        parts: ['Otherwise hold the stronger of', sym('VTI'), sym('VXUS')],
        funds: [
          { symbol: 'VTI', weight: '100%', ifPicked: true },
          { symbol: 'VXUS', weight: '100%', ifPicked: true },
        ],
      },
    ],
    versions: [{ n: 1, saved: 'Nov 6', note: 'First version' }],
    seed: 53,
  },
  {
    id: 'risk-parity',
    name: 'Risk Parity',
    state: 'never-run',
    version: 1,
    cadence: 'monthly',
    summary: 'Weights stocks, bonds and gold so each adds the same risk.',
    rules: [
      {
        parts: [
          'Weight',
          sym('VTI'),
          sym('TLT'),
          sym('GLD'),
          'by inverse',
          num('60-day'),
          'volatility',
        ],
        funds: [
          { symbol: 'TLT', weight: 'about 45%' },
          { symbol: 'GLD', weight: 'about 30%' },
          { symbol: 'VTI', weight: 'about 25%' },
        ],
      },
    ],
    versions: [{ n: 1, saved: 'Oct 28', note: 'First version' }],
    seed: 61,
  },
  {
    id: 'pullback-buyer',
    name: 'Pullback Buyer',
    state: 'draft',
    version: 1,
    cadence: 'daily',
    summary: 'Buys SPY after three down days, sells after five up days.',
    rules: [
      { parts: ['Buy', sym('SPY'), 'after', num('3'), 'down days in a row'] },
      { parts: ['Sell after', num('5'), 'up days, or a', num('4%'), 'drop from entry'] },
    ],
    versions: [{ n: 1, saved: 'Nov 17', note: 'Draft, not saved as a version yet' }],
    seed: 71,
  },
];

export const SESSIONS: Session[] = [
  {
    id: 's-aw',
    strategyId: 'all-weather',
    mode: 'live',
    version: 2,
    value: 48_413.97,
    today: -190.82,
    started: 'Aug 4',
    holds: [
      { symbol: 'VGLT', weight: 43.9 },
      { symbol: 'VTI', weight: 28.0 },
      { symbol: 'IEF', weight: 14.2 },
      { symbol: 'DBC', weight: 7.1 },
      { symbol: 'GLD', weight: 6.8 },
    ],
    next: 'Rebalance Dec 1',
  },
  {
    id: 's-rr',
    strategyId: 'recession-radar',
    mode: 'paper',
    version: 3,
    value: 31_867.77,
    today: -207.11,
    started: 'Nov 4',
    holds: [
      { symbol: 'TLT', weight: 60.2 },
      { symbol: 'GLD', weight: 39.8 },
    ],
    next: 'Checks at each close',
  },
  {
    id: 's-ms',
    strategyId: 'momentum-sectors',
    mode: 'paper',
    version: 5,
    value: 21_916.57,
    today: -195.86,
    started: 'Nov 9',
    holds: [
      { symbol: 'XLC', weight: 33.5 },
      { symbol: 'XLF', weight: 33.3 },
      { symbol: 'XLI', weight: 33.2 },
    ],
    next: 'Rebalance Nov 23',
  },
  {
    id: 's-tm',
    strategyId: 'tech-momentum',
    mode: 'paper',
    version: 4,
    value: 26_198.65,
    today: 0,
    started: 'Oct 8',
    stoppedOn: 'Nov 12',
    holds: [],
  },
];

export const BACKTESTS: Backtest[] = [
  {
    id: 'b1',
    strategyId: 'momentum-sectors',
    version: 5,
    ran: 'Nov 16',
    range: 'Nov 2024 to Nov 2026',
    ret: 0.175,
    spy: 0.219,
    worst: -0.168,
    sharpe: 0.48,
    seed: 37,
  },
  {
    id: 'b2',
    strategyId: 'recession-radar',
    version: 3,
    ran: 'Nov 16',
    range: 'Nov 2024 to Nov 2026',
    ret: 0.223,
    spy: 0.219,
    worst: -0.147,
    sharpe: 0.58,
    seed: 23,
  },
  {
    id: 'b3',
    strategyId: 'all-weather',
    version: 2,
    ran: 'Nov 16',
    range: 'Nov 2024 to Nov 2026',
    ret: 0.088,
    spy: 0.219,
    worst: -0.074,
    sharpe: 0.37,
    seed: 11,
  },
  {
    id: 'b4',
    strategyId: 'dual-momentum',
    version: 1,
    ran: 'Nov 10',
    range: 'Nov 2024 to Nov 2026',
    ret: 0.106,
    spy: 0.219,
    worst: -0.12,
    sharpe: 0.29,
    seed: 53,
  },
  {
    id: 'b5',
    strategyId: 'risk-parity',
    version: 1,
    ran: 'Oct 28',
    range: 'Nov 2024 to Oct 2026',
    ret: 0.1,
    spy: 0.201,
    worst: -0.046,
    sharpe: 1.11,
    seed: 61,
  },
  {
    id: 'b6',
    strategyId: 'tech-momentum',
    version: 4,
    ran: 'Oct 8',
    range: 'Oct 2024 to Oct 2026',
    ret: 0.174,
    spy: 0.188,
    worst: -0.148,
    sharpe: 0.41,
    seed: 41,
  },
];

export const strategyById = (id: string) => STRATEGIES.find((s) => s.id === id);
export const sessionFor = (strategyId: string) =>
  SESSIONS.find((s) => s.strategyId === strategyId && !s.stoppedOn);
export const backtestsFor = (strategyId: string) =>
  BACKTESTS.filter((b) => b.strategyId === strategyId);

/** Seeded weekly series ending at `end` total return, shaped by a shared market path so lines move together. */
export function series(seed: number, end: number, points = 104): number[] {
  let s = seed * 7919 + 17;
  const rnd = () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
  const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-9)) * Math.cos(2 * Math.PI * rnd());
  const raw = [1];
  for (let i = 1; i < points; i++) raw.push(raw[i - 1] * (1 + gauss() * 0.018));
  const drift = Math.pow((1 + end) / raw[points - 1], 1 / (points - 1));
  return raw.map((v, i) => 100 * v * Math.pow(drift, i));
}

export const usd = (v: number) =>
  v.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
export const signedUsd = (v: number) => `${v >= 0 ? '+' : '−'}${usd(Math.abs(v))}`;
export const pct = (v: number, digits = 1) =>
  `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(digits)}%`;

export const stateLabel = (s: Strategy) =>
  s.state === 'running'
    ? `Running on ${s.mode}`
    : s.state === 'stopped'
      ? `Stopped ${s.stoppedOn}`
      : s.state === 'never-run'
        ? 'Never run'
        : 'Draft';

/* ---------- Sample history ---------- */

/**
 * Sample closes and values behind Home's longer ranges, as [ISO date, value]. Each series meets the
 * figures above (and the session stories' Nov 12 and Nov 13 closes) at its end; the shape in between
 * is sample data, and Home says so.
 */
export const SAMPLE_SPY_CLOSES: [string, number][] = [
  ['2025-11-20', 633.3],
  ['2026-01-02', 640.2],
  ['2026-04-08', 631.4],
  ['2026-06-15', 668.1],
  ['2026-08-04', 650.29],
  ['2026-08-20', 663.17],
  ['2026-09-24', 701.6],
  ['2026-10-08', 688.97],
  ['2026-10-20', 720.2],
  ['2026-11-04', 711.49],
  ['2026-11-09', 716.57],
  ['2026-11-12', 712.4],
  ['2026-11-13', 704.85],
];

/** The whole account as an index, 100 on Nov 20, 2025. Sample. */
export const SAMPLE_ACCOUNT_INDEX: [string, number][] = [
  ['2025-11-20', 100],
  ['2026-01-02', 101.58],
  ['2026-04-08', 99.6],
  ['2026-06-15', 103.9],
  ['2026-08-20', 107.14],
  ['2026-09-24', 109.4],
  ['2026-10-20', 110.6],
  ['2026-11-12', 110.9],
];

/** Each session's value before yesterday, from its start. Yesterday and today come from `SESSIONS`. Sample. */
export const SAMPLE_SESSION_VALUES: Record<string, [string, number][]> = {
  's-aw': [
    ['2026-08-04', 46_000],
    ['2026-08-20', 47_100],
    ['2026-10-20', 48_706],
  ],
  's-rr': [
    ['2026-11-04', 31_200],
    ['2026-11-13', 31_580],
  ],
  's-ms': [
    ['2026-11-09', 21_500],
    ['2026-11-16', 21_880],
  ],
  's-tm': [
    ['2026-10-08', 25_000],
    ['2026-10-20', 27_404],
  ],
};

/** Fund returns over each range, in percent. Sample. Today's change comes from the quotes. */
export const SAMPLE_FUND_RETURNS: Record<string, Record<'1M' | '3M' | 'YTD' | '1Y', number>> = {
  VGLT: { '1M': 1.9, '3M': 0.6, YTD: 2.9, '1Y': 2.0 },
  TLT: { '1M': 2.2, '3M': 0.9, YTD: 3.1, '1Y': 1.6 },
  IEF: { '1M': 0.8, '3M': 0.7, YTD: 3.6, '1Y': 4.1 },
  VTI: { '1M': -3.2, '3M': 1.6, YTD: 10.8, '1Y': 13.1 },
  XLC: { '1M': -2.4, '3M': 3.1, YTD: 14.2, '1Y': 16.0 },
  XLF: { '1M': -3.6, '3M': 0.8, YTD: 9.6, '1Y': 12.4 },
  XLI: { '1M': -2.9, '3M': 1.2, YTD: 10.4, '1Y': 12.8 },
  GLD: { '1M': -1.2, '3M': 6.5, YTD: 24.0, '1Y': 31.0 },
  DBC: { '1M': -1.8, '3M': -0.6, YTD: 3.1, '1Y': 1.9 },
};

/** SPY's 200-day average. Nov 12 and Nov 13 are from Recession Radar's rebalance; the rest is sample. */
export const SAMPLE_SPY_200D: [string, number][] = [
  ['2026-10-20', 703.6],
  ['2026-11-12', 708.1],
  ['2026-11-13', 708.62],
  ['2026-11-20', 709.9],
];

/** 90-day returns of the sector funds Momentum Sectors ranks, top six of eleven. Sample. */
export const SAMPLE_SECTOR_RANKS: { symbol: string; name: string; ret: number }[] = [
  { symbol: 'XLF', name: 'Financials', ret: 9.8 },
  { symbol: 'XLC', name: 'Communication', ret: 9.1 },
  { symbol: 'XLI', name: 'Industrials', ret: 8.4 },
  { symbol: 'XLK', name: 'Technology', ret: 7.9 },
  { symbol: 'XLV', name: 'Health care', ret: 5.2 },
  { symbol: 'XLY', name: 'Consumer discretionary', ret: 4.6 },
];
