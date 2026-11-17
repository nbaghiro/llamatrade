import {
  dayKey,
  drawdownOf,
  type RebalanceFrequency,
  type TradeInput,
} from '../../lib/backtestView';
import { formatPct } from '../../lib/format';

const DAY_MS = 86_400_000;
/** Held stretches this close together (a weekend, a holiday) read as one. */
const MERGE_GAP_DAYS = 4;

export interface HeldSpan {
  from: Date;
  to: Date;
}

export interface HoldingLane {
  symbol: string;
  spans: HeldSpan[];
  /** Calendar days held across the window, for ordering and grouping. */
  days: number;
}

const utcDay = (d: Date) => new Date(`${dayKey(d)}T00:00:00Z`);

function mergeSpans(spans: readonly HeldSpan[]): HeldSpan[] {
  const sorted = [...spans].sort((a, b) => a.from.getTime() - b.from.getTime());
  const out: HeldSpan[] = [];
  for (const s of sorted) {
    const last = out[out.length - 1];
    if (last && s.from.getTime() - last.to.getTime() <= MERGE_GAP_DAYS * DAY_MS) {
      if (s.to.getTime() > last.to.getTime()) last.to = s.to;
    } else {
      out.push({ from: s.from, to: s.to });
    }
  }
  return out;
}

/**
 * When each symbol was held, rebuilt from the trade list's entry and exit dates and clipped to
 * the window. A trade still open at the end runs to `end`. Longest-held symbols come first.
 */
export function holdingLanes(trades: readonly TradeInput[], start: Date, end: Date): HoldingLane[] {
  const bySymbol = new Map<string, HeldSpan[]>();
  for (const t of trades) {
    if (!t.entryTime) continue;
    const from = utcDay(t.entryTime);
    const to = t.exitTime ? utcDay(t.exitTime) : end;
    if (to.getTime() < start.getTime() || from.getTime() > end.getTime()) continue;
    const clipped = {
      from: from.getTime() < start.getTime() ? start : from,
      to: to.getTime() > end.getTime() ? end : to,
    };
    const list = bySymbol.get(t.symbol) ?? [];
    list.push(clipped);
    bySymbol.set(t.symbol, list);
  }
  return [...bySymbol.entries()]
    .map(([symbol, spans]) => {
      const merged = mergeSpans(spans);
      const days = merged.reduce((s, x) => s + (x.to.getTime() - x.from.getTime()) / DAY_MS, 0);
      return { symbol, spans: merged, days };
    })
    .sort((a, b) => b.days - a.days || a.symbol.localeCompare(b.symbol));
}

/** At most `max` lanes; past that, the rest share one lane named for how many they are. */
export function foldLanes(lanes: readonly HoldingLane[], max: number): HoldingLane[] {
  if (lanes.length <= max) return [...lanes];
  const kept = lanes.slice(0, max - 1);
  const rest = lanes.slice(max - 1);
  const spans = mergeSpans(rest.flatMap((l) => l.spans));
  return [
    ...kept,
    {
      symbol: `${rest.length} more`,
      spans,
      days: rest.reduce((s, l) => s + l.days, 0),
    },
  ];
}

export interface RebalanceMark {
  at: Date;
  /** The set of symbols held changed on this day. */
  switched: boolean;
  orders: number;
}

function heldOn(trades: readonly TradeInput[], key: string, after: boolean): Set<string> {
  const held = new Set<string>();
  for (const t of trades) {
    if (!t.entryTime) continue;
    const a = dayKey(t.entryTime);
    const b = t.exitTime ? dayKey(t.exitTime) : null;
    const opened = after ? a <= key : a < key;
    const open = b === null || (after ? b > key : b >= key);
    if (opened && open) held.add(t.symbol);
  }
  return held;
}

const sameSet = (a: Set<string>, b: Set<string>) =>
  a.size === b.size && [...a].every((x) => b.has(x));

/**
 * One mark per trading day with orders, oldest first. There is no rebalance log, so a day with
 * fills stands for a rebalance, and a switch is one where the held symbols changed.
 */
export function rebalanceMarks(trades: readonly TradeInput[]): RebalanceMark[] {
  const counts = new Map<string, number>();
  for (const t of trades) {
    if (t.entryTime) counts.set(dayKey(t.entryTime), (counts.get(dayKey(t.entryTime)) ?? 0) + 1);
    if (t.exitTime) counts.set(dayKey(t.exitTime), (counts.get(dayKey(t.exitTime)) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([key, orders]) => ({
      at: new Date(`${key}T00:00:00Z`),
      switched: !sameSet(heldOn(trades, key, false), heldOn(trades, key, true)),
      orders,
    }));
}

export interface WorstStretch {
  peak: Date;
  trough: Date;
  /** Back at the previous peak; null when it never got back inside the window. */
  recovered: Date | null;
  /** Negative fraction. */
  depth: number;
  peakValue: number;
}

/** The deepest fall from a running peak, with where it started, bottomed and recovered. */
export function worstStretch(
  dates: readonly Date[],
  values: readonly number[]
): WorstStretch | null {
  if (dates.length < 2 || values.length < 2) return null;
  const dd = drawdownOf(values);
  let low = 0;
  dd.forEach((d, i) => {
    if (d < dd[low]) low = i;
  });
  if (dd[low] >= 0) return null;
  let peak = low;
  while (peak > 0 && dd[peak] < 0) peak--;
  let recovered: number | null = null;
  for (let i = low + 1; i < values.length; i++) {
    if (dd[i] >= 0) {
      recovered = i;
      break;
    }
  }
  return {
    peak: dates[peak],
    trough: dates[low],
    recovered: recovered === null ? null : dates[recovered],
    depth: dd[low],
    peakValue: values[peak],
  };
}

/** Days between two dates, rounded. */
export function daysBetween(a: Date, b: Date): number {
  return Math.round(Math.abs(b.getTime() - a.getTime()) / DAY_MS);
}

/** Years covered by the window; long runs read better on a log scale. */
export function yearsBetween(a: Date, b: Date): number {
  return (b.getTime() - a.getTime()) / (365.25 * DAY_MS);
}

export const LOG_SCALE_FROM_YEARS = 5;

/** Values on a log scale for drawing; non-positive values break the line. */
export function toLog(values: readonly number[]): number[] {
  return values.map((v) => (v > 0 ? Math.log(v) : Number.NaN));
}

/** Scheduled rebalance dates: the first trading day of each period between start and end. */
export function scheduleDates(start: Date, end: Date, stepMonths: number): Date[] {
  if (stepMonths <= 0 || end.getTime() < start.getTime()) return [];
  const out: Date[] = [];
  let y = start.getUTCFullYear();
  let m = start.getUTCMonth();
  for (let k = 0; k < 1200; k++) {
    let d = new Date(Date.UTC(y, m, 1));
    if (d.getTime() < start.getTime()) d = start;
    while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d = new Date(d.getTime() + DAY_MS);
    if (d.getTime() > end.getTime()) break;
    out.push(d);
    m += stepMonths;
    y += Math.floor(m / 12);
    m %= 12;
  }
  return out;
}

/**
 * At most `max` marks across the window: marks that would overlap share one, which is a
 * switch when any of them is, and carries their combined order count.
 */
export function thinMarks(
  marks: readonly RebalanceMark[],
  start: Date,
  end: Date,
  max: number
): { marks: RebalanceMark[]; thinned: boolean } {
  if (marks.length <= max) return { marks: [...marks], thinned: false };
  const span = Math.max(1, end.getTime() - start.getTime());
  const buckets = new Map<number, RebalanceMark>();
  for (const m of marks) {
    const k = Math.min(max - 1, Math.floor(((m.at.getTime() - start.getTime()) / span) * max));
    const prev = buckets.get(k);
    buckets.set(
      k,
      prev
        ? { at: prev.at, switched: prev.switched || m.switched, orders: prev.orders + m.orders }
        : { ...m }
    );
  }
  return {
    marks: [...buckets.entries()].sort(([a], [b]) => a - b).map(([, m]) => m),
    thinned: true,
  };
}

/** The symbols held on a day, from the merged holding spans. */
export function heldSymbolsOn(lanes: readonly HoldingLane[], day: Date): string[] {
  const t = day.getTime();
  return lanes
    .filter((l) => l.spans.some((s) => s.from.getTime() <= t && t < s.to.getTime()))
    .map((l) => l.symbol)
    .sort();
}

export interface HeldStretch {
  from: Date;
  to: Date;
  symbols: string[];
}

/** A run's holdings as consecutive stretches of the same symbols, sampled on `dates`. */
export function heldStretches(
  lanes: readonly HoldingLane[],
  dates: readonly Date[]
): HeldStretch[] {
  const out: HeldStretch[] = [];
  for (const d of dates) {
    const symbols = heldSymbolsOn(lanes, d);
    const last = out[out.length - 1];
    if (last && last.symbols.join(',') === symbols.join(',')) last.to = d;
    else out.push({ from: d, to: d, symbols });
  }
  return out;
}

export interface DiffStretch {
  from: Date;
  to: Date;
  /** What `a`'s value over `b`'s changed by across the stretch, as a fraction. */
  gained: number;
  days: number;
}

/**
 * Stretches where two runs held different symbols, on shared `dates` with both series rebased
 * to the same start, and what each stretch was worth to the first run.
 */
export function differingStretches(
  dates: readonly Date[],
  a: readonly number[],
  b: readonly number[],
  aLanes: readonly HoldingLane[],
  bLanes: readonly HoldingLane[]
): DiffStretch[] {
  const out: DiffStretch[] = [];
  let open: number | null = null;
  const close = (i: number, end: number) => {
    const before = i > 0 ? a[i - 1] / b[i - 1] : a[i] / b[i];
    out.push({
      from: dates[i],
      to: dates[end],
      gained: a[end] / b[end] / before - 1,
      days: end - i + 1,
    });
  };
  for (let i = 0; i < dates.length; i++) {
    const differs =
      heldSymbolsOn(aLanes, dates[i]).join(',') !== heldSymbolsOn(bLanes, dates[i]).join(',');
    if (differs && open === null) open = i;
    if (!differs && open !== null) {
      close(open, i - 1);
      open = null;
    }
  }
  if (open !== null) close(open, dates.length - 1);
  return out;
}

const shortDate = (d: Date) =>
  d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });

/** Pin text for the worst fall: "−6.6% · Mar 3 to Jun 5, 2025". */
export function stretchLabel(w: WorstStretch): string {
  const depth = formatPct(w.depth, { dp: 1 });
  return w.recovered
    ? `${depth} · ${shortDate(w.peak)} to ${shortDate(w.recovered)}`
    : `${depth} · from ${shortDate(w.peak)}, not recovered`;
}

const STEP_MONTHS: Partial<Record<RebalanceFrequency, number>> = {
  monthly: 1,
  quarterly: 3,
  annually: 12,
};

/** Scheduled rebalance dates for calendar schedules; empty for daily and weekly. */
export function scheduleFor(
  start: Date | null,
  end: Date | null,
  rebalance: RebalanceFrequency | null
): Date[] {
  const step = rebalance ? STEP_MONTHS[rebalance] : undefined;
  return start && end && step ? scheduleDates(start, end, step) : [];
}

/** Symbols held on more than half of the `dates` between `from` and `to`. */
export function mostlyHeld(
  lanes: readonly HoldingLane[],
  dates: readonly Date[],
  from: Date,
  to: Date
): string[] {
  const inside = dates.filter((d) => d.getTime() >= from.getTime() && d.getTime() <= to.getTime());
  if (!inside.length) return [];
  const counts = new Map<string, number>();
  for (const d of inside) {
    for (const s of heldSymbolsOn(lanes, d)) counts.set(s, (counts.get(s) ?? 0) + 1);
  }
  return [...counts.entries()]
    .filter(([, n]) => n * 2 > inside.length)
    .map(([s]) => s)
    .sort();
}
