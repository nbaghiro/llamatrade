/** The benchmark's worst stretches in a backtest, and how the strategy did in each (performance2 C). */

const DAY_MS = 86_400_000;
const MONTH_MS = 30.44 * DAY_MS;

/** A fall in the benchmark of more than this fraction from its running high counts. */
export const STRESS_THRESHOLD = 0.1;

export interface StressPeriod {
  /** 1-based, in date order. */
  n: number;
  /** The benchmark's high before the fall. */
  start: Date;
  /** The benchmark's lowest point before it recovered. */
  trough: Date;
  /** When the benchmark got back to its high; null when it hasn't yet. */
  recovered: Date | null;
  /** Benchmark change from high to low, a negative fraction. */
  benchDrop: number;
  /** The strategy's largest fall from its own high between `start` and `trough`, a fraction (0 or negative). */
  strategyDrop: number;
  /** When the strategy got back to the high it had going in; null when it hasn't yet. */
  strategyBack: Date | null;
  /** Whole months from the strategy's low to `strategyBack`; null when not back yet. */
  monthsBack: number | null;
}

/**
 * Stretches where `bench` fell more than `threshold` from a running high. Each runs from the
 * high to the low reached before the benchmark recovered that high. `strategy` shares `dates`.
 */
export function findStressPeriods(
  dates: readonly Date[],
  bench: readonly number[],
  strategy: readonly number[],
  threshold = STRESS_THRESHOLD
): StressPeriod[] {
  const n = Math.min(dates.length, bench.length, strategy.length);
  const out: StressPeriod[] = [];
  let peakI = 0;
  let troughI = -1;
  const close = (recoveredI: number | null) => {
    if (troughI < 0) return;
    const drop = bench[troughI] / bench[peakI] - 1;
    if (drop < -threshold) {
      out.push({
        n: out.length + 1,
        start: dates[peakI],
        trough: dates[troughI],
        recovered: recoveredI === null ? null : dates[recoveredI],
        benchDrop: drop,
        ...strategyStretch(dates, strategy, peakI, troughI, n),
      });
    }
  };
  for (let i = 0; i < n; i++) {
    const v = bench[i];
    if (!Number.isFinite(v) || v <= 0) continue;
    if (v >= bench[peakI]) {
      close(troughI >= 0 ? i : null);
      peakI = i;
      troughI = -1;
    } else if (troughI < 0 || v < bench[troughI]) {
      troughI = i;
    }
  }
  close(null);
  return out.map((p, i) => ({ ...p, n: i + 1 }));
}

function strategyStretch(
  dates: readonly Date[],
  strategy: readonly number[],
  from: number,
  to: number,
  n: number
): Pick<StressPeriod, 'strategyDrop' | 'strategyBack' | 'monthsBack'> {
  let high = strategy[from];
  let highBefore = high;
  let worst = 0;
  let lowI = from;
  for (let i = from; i <= to; i++) {
    if (strategy[i] > high) high = strategy[i];
    const dd = high > 0 ? strategy[i] / high - 1 : 0;
    if (dd < worst) {
      worst = dd;
      lowI = i;
      highBefore = high;
    }
  }
  if (worst === 0) return { strategyDrop: 0, strategyBack: null, monthsBack: 0 };
  for (let i = lowI + 1; i < n; i++) {
    if (strategy[i] >= highBefore) {
      return {
        strategyDrop: worst,
        strategyBack: dates[i],
        monthsBack: Math.max(
          1,
          Math.round((dates[i].getTime() - dates[lowI].getTime()) / MONTH_MS)
        ),
      };
    }
  }
  return { strategyDrop: worst, strategyBack: null, monthsBack: null };
}

/** Names for well-known market falls, matched on the month the stretch began. */
const KNOWN: readonly { from: string; to: string; name: string }[] = [
  { from: '2018-01-15', to: '2018-02-28', name: 'Volatility spike' },
  { from: '2018-09-01', to: '2018-12-31', name: 'Late 2018 sell-off' },
  { from: '2020-02-01', to: '2020-03-31', name: 'Covid sell-off' },
  { from: '2021-12-15', to: '2022-08-31', name: 'Rate rises' },
  { from: '2025-02-01', to: '2025-04-30', name: 'Tariff sell-off' },
];

/** The common name for the fall that began on `start`, or null when it has none. */
export function periodName(start: Date): string | null {
  const iso = start.toISOString().slice(0, 10);
  return KNOWN.find((k) => iso >= k.from && iso <= k.to)?.name ?? null;
}

/** A trade with an entry and, once closed, an exit. */
export interface HeldTrade {
  symbol: string;
  entry: Date;
  exit: Date | null;
}

export interface HeldGroup {
  symbols: string[];
  from: Date;
}

export type HeldGoingIn =
  | { kind: 'unknown' }
  | { kind: 'cash'; then: HeldGroup | null; more: number }
  | { kind: 'held'; groups: HeldGroup[]; then: HeldGroup | null; more: number };

const sameDay = (a: Date, b: Date) =>
  Math.floor(a.getTime() / DAY_MS) === Math.floor(b.getTime() / DAY_MS);

function byEntryDay(trades: readonly HeldTrade[]): HeldGroup[] {
  const groups: HeldGroup[] = [];
  for (const t of [...trades].sort((a, b) => a.entry.getTime() - b.entry.getTime())) {
    const g = groups.find((x) => sameDay(x.from, t.entry));
    if (g) {
      if (!g.symbols.includes(t.symbol)) g.symbols.push(t.symbol);
    } else {
      groups.push({ symbols: [t.symbol], from: t.entry });
    }
  }
  return groups;
}

/**
 * What the strategy held at `start`, grouped by the day each position opened, then the first
 * day it bought something before `trough` and how many more buying days followed.
 * `unknown` when the run recorded no trades at all.
 */
export function heldGoingIn(
  trades: readonly HeldTrade[] | null,
  start: Date,
  trough: Date
): HeldGoingIn {
  if (!trades || trades.length === 0) return { kind: 'unknown' };
  const t0 = start.getTime();
  const t1 = trough.getTime();
  const open = byEntryDay(
    trades.filter((t) => t.entry.getTime() <= t0 && (!t.exit || t.exit.getTime() > t0))
  );
  const added = byEntryDay(trades.filter((t) => t.entry.getTime() > t0 && t.entry.getTime() <= t1));
  const then = added[0] ?? null;
  const more = Math.max(0, added.length - 1);
  if (!open.length) return { kind: 'cash', then, more };
  return { kind: 'held', groups: open, then, more };
}

/** "TLT and GLD", "QQQ, VTI and IWM". */
export function andList(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? '';
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** The values scaled so their first finite value equals `to`. */
export function rebase(values: readonly number[], to: number): number[] {
  const first = values.find((v) => Number.isFinite(v) && v > 0);
  if (!first) return values.map(() => NaN);
  return values.map((v) => (v / first) * to);
}
