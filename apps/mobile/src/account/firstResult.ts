/** Reading a first backtest: what it held and when, where it switched, and its worst drop (first-result2 A). */

export interface TradeLeg {
  symbol: string;
  entryTime: Date | null;
  exitTime: Date | null;
}

export interface HeldPeriod {
  /** The symbols held, sorted and joined: "GLD · TLT". */
  key: string;
  symbols: string[];
  from: Date;
  to: Date;
}

const DAY = 86_400_000;
const dayStart = (d: Date) => Math.floor(d.getTime() / DAY) * DAY;

/** One period per run of days with the same set of symbols, from the round-trip trades. Days in cash make no period. */
export function heldPeriods(trades: readonly TradeLeg[], end: Date): HeldPeriod[] {
  const endMs = dayStart(end);
  const legs = trades
    .filter((t): t is TradeLeg & { entryTime: Date } => t.entryTime !== null)
    .map((t) => ({ symbol: t.symbol, from: dayStart(t.entryTime), to: t.exitTime ? dayStart(t.exitTime) : Infinity }));
  const bounds = [...new Set(legs.flatMap((l) => [l.from, l.to]))]
    .filter((b) => Number.isFinite(b) && b <= endMs)
    .sort((a, b) => a - b);

  const periods: HeldPeriod[] = [];
  bounds.forEach((b, i) => {
    const to = i + 1 < bounds.length ? bounds[i + 1] : endMs;
    if (to <= b) return;
    const symbols = [...new Set(legs.filter((l) => l.from <= b && l.to > b).map((l) => l.symbol))].sort();
    if (symbols.length === 0) return;
    const key = symbols.join(' · ');
    const last = periods[periods.length - 1];
    if (last && last.key === key && last.to.getTime() === b) {
      last.to = new Date(to);
    } else {
      periods.push({ key, symbols, from: new Date(b), to: new Date(to) });
    }
  });
  return periods;
}

export interface HoldingLane {
  key: string;
  symbols: string[];
  /** Stretches as fractions of the run, 0 to 1. */
  spans: { from: number; to: number }[];
  days: number;
}

/** The distinct sets held as lanes on the run's x axis, most days first, at most `max` lanes. */
export function holdingLanes(periods: readonly HeldPeriod[], start: Date, end: Date, max = 3): HoldingLane[] {
  const t0 = start.getTime();
  const span = Math.max(1, end.getTime() - t0);
  const frac = (d: Date) => Math.min(1, Math.max(0, (d.getTime() - t0) / span));
  const lanes = new Map<string, HoldingLane>();
  for (const p of periods) {
    const lane = lanes.get(p.key) ?? { key: p.key, symbols: p.symbols, spans: [], days: 0 };
    lane.spans.push({ from: frac(p.from), to: frac(p.to) });
    lane.days += Math.round((p.to.getTime() - p.from.getTime()) / DAY);
    lanes.set(p.key, lane);
  }
  return [...lanes.values()].sort((a, b) => b.days - a.days).slice(0, max);
}

/** The days the holdings changed from one set to another, after the first purchase. */
export function switchesOf(periods: readonly HeldPeriod[]): HeldPeriod[] {
  return periods.slice(1);
}

export function drawdownOf(values: readonly number[]): number[] {
  let peak = -Infinity;
  return values.map((v) => {
    peak = Math.max(peak, v);
    return peak > 0 ? v / peak - 1 : 0;
  });
}

/** The deepest fall below a running peak, as a negative fraction; 0 when the curve never fell. */
export function maxDrawdown(values: readonly number[]): number {
  return values.length ? Math.min(0, ...drawdownOf(values)) : 0;
}

/** "TLT and GLD", or "BIL, BND, GLD and 4 more" for long sets. */
export function symbolsLabel(symbols: readonly string[], max = 3): string {
  if (symbols.length <= 2) return symbols.join(' and ');
  if (symbols.length <= max) return `${symbols.slice(0, -1).join(', ')} and ${symbols[symbols.length - 1]}`;
  return `${symbols.slice(0, max).join(', ')} and ${symbols.length - max} more`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Mar 24, 2025". */
export function dayLabel(d: Date): string {
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

/** "Nov 2024". */
export function monthLabel(d: Date): string {
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/**
 * The sentence under the lanes: which set it moved into most often and on which dates, or null
 * when it never switched. Says nothing about why the curve moved, which the data can't show.
 */
export function switchSentence(periods: readonly HeldPeriod[]): string | null {
  const switches = switchesOf(periods);
  if (switches.length === 0) return null;
  const counts = new Map<string, HeldPeriod[]>();
  for (const p of switches) counts.set(p.key, [...(counts.get(p.key) ?? []), p]);
  const [, into] = [...counts.entries()].sort((a, b) => b[1].length - a[1].length)[0];
  const label = symbolsLabel(into[0].symbols);
  const dates = into.map((p) => dayLabel(p.from));
  const times = into.length === 1 ? 'once' : into.length === 2 ? 'twice' : `${into.length} times`;
  const list = dates.length <= 3 ? dates.join(' and ').replace(/ and (?=.* and )/, ', ') : `${dates.slice(0, 2).join(', ')} and ${dates.length - 2} more`;
  return `Switched into ${label} ${times}: ${list}.`;
}

/** At most this many switch pins on a phone curve; past it the pins become noise. */
export const MAX_PINS = 8;

/** One lane per symbol, for strategies that hold many different sets; most days first. */
export function symbolLanes(periods: readonly HeldPeriod[], start: Date, end: Date, max = 4): HoldingLane[] {
  const perSymbol: HeldPeriod[] = [];
  for (const p of periods) {
    for (const sym of p.symbols) perSymbol.push({ key: sym, symbols: [sym], from: p.from, to: p.to });
  }
  const lanes = holdingLanes(perSymbol, start, end, max);
  for (const lane of lanes) {
    const merged: { from: number; to: number }[] = [];
    for (const sp of [...lane.spans].sort((a, b) => a.from - b.from)) {
      const last = merged[merged.length - 1];
      if (last && sp.from <= last.to + 1e-9) last.to = Math.max(last.to, sp.to);
      else merged.push({ ...sp });
    }
    lane.spans = merged;
  }
  return lanes;
}

/** Set lanes when the strategy moves between a few sets, symbol lanes when it rotates through many. */
export function resultLanes(periods: readonly HeldPeriod[], start: Date, end: Date): { lanes: HoldingLane[]; bySymbol: boolean } {
  const sets = new Set(periods.map((p) => p.key)).size;
  if (sets <= 3) return { lanes: holdingLanes(periods, start, end, 3), bySymbol: false };
  return { lanes: symbolLanes(periods, start, end, 4), bySymbol: true };
}

/** The sentence under the lanes, or a count when it changed holdings too often to list. */
export function resultSentence(periods: readonly HeldPeriod[]): string | null {
  const n = switchesOf(periods).length;
  if (n > MAX_PINS) return `Changed its holdings ${n} times over the run. The lanes show its most-held symbols.`;
  return switchSentence(periods);
}
