/**
 * Reading a backtest on the phone (backtests/phone A, results2 A, setup2 A, running2 A,
 * failed A): its worst stretch, a sentence against the benchmark, range presets and progress.
 * Plain data, so it runs under `node --test`.
 */

export interface Point {
  /** Epoch ms. */
  at: number;
  value: number;
}

const DAY_MS = 86_400_000;
const YEAR_MS = 365.25 * DAY_MS;

/** Total return of a series as a fraction; null with fewer than two positive points. */
export function totalReturn(points: readonly Point[]): number | null {
  if (points.length < 2 || points[0].value <= 0) return null;
  return points[points.length - 1].value / points[0].value - 1;
}

export interface Stretch {
  /** The peak before the fall. */
  from: number;
  /** The lowest point. */
  to: number;
  /** As a negative fraction. */
  depth: number;
  /** The first day back at the peak, or null if it never got back. */
  recovered: number | null;
}

/** The deepest fall from a running peak; null for a series that never fell. */
export function worstStretch(points: readonly Point[]): Stretch | null {
  let peak: Point | null = null;
  let best: Stretch | null = null;
  for (const p of points) {
    if (!peak || p.value >= peak.value) {
      peak = p;
      continue;
    }
    const depth = p.value / peak.value - 1;
    if (!best || depth < best.depth) best = { from: peak.at, to: p.at, depth, recovered: null };
  }
  if (!best) return null;
  const peakValue = points.find((p) => p.at === best.from)?.value ?? 0;
  const back = points.find((p) => p.at > best.to && p.value >= peakValue);
  return { ...best, recovered: back ? back.at : null };
}

/** Annual growth rate over the dates, as a fraction; null under a month. */
export function cagr(total: number, start: number, end: number): number | null {
  const years = (end - start) / YEAR_MS;
  if (years < 1 / 12 || total <= -1) return null;
  return (1 + total) ** (1 / years) - 1;
}

/**
 * "17.4 points less than SPY, with less than half of its worst drawdown." Both returns and
 * drawdowns are fractions; drawdowns negative. Null without a benchmark return.
 */
export function resultSentence(ret: number, benchRet: number | null, dd: number | null, benchDd: number | null, bench: string): string | null {
  if (benchRet === null) return null;
  const pts = Math.abs((ret - benchRet) * 100).toFixed(1);
  const lead = pts === '0.0' ? `Level with ${bench}` : `${pts} points ${ret > benchRet ? 'more' : 'less'} than ${bench}`;
  if (dd === null || benchDd === null || benchDd >= 0) return `${lead}.`;
  const ratio = Math.abs(dd) / Math.abs(benchDd);
  const tail =
    ratio < 0.5
      ? 'with less than half of its worst drawdown'
      : ratio < 0.95
        ? 'with a smaller worst drawdown'
        : ratio <= 1.05
          ? 'with about the same worst drawdown'
          : 'with a deeper worst drawdown';
  return `${lead}, ${tail}.`;
}

export type RangePreset = '1Y' | '3Y' | '5Y' | 'Max';
export const RANGE_PRESETS: readonly RangePreset[] = ['1Y', '3Y', '5Y', 'Max'];

const MAX_YEARS = 10;

/** ISO date (YYYY-MM-DD) of a UTC time. */
export function isoDay(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

/**
 * A preset's start and end, ending today. Max starts at the earliest date every symbol has
 * prices for when known, else ten years back.
 */
export function presetRange(preset: RangePreset, today: number, earliest: number | null = null): { start: number; end: number } {
  const d = new Date(today);
  const years = preset === 'Max' ? MAX_YEARS : Number(preset.slice(0, -1));
  const start = Date.UTC(d.getUTCFullYear() - years, d.getUTCMonth(), d.getUTCDate());
  if (preset === 'Max' && earliest !== null) return { start: Math.max(earliest, start), end: today };
  return { start, end: today };
}

/** How many times a cadence rebalances between two dates (calendar arithmetic, not trading days). */
export function rebalanceCount(cadence: string, start: number, end: number): number | null {
  if (end <= start) return 0;
  const days = (end - start) / DAY_MS;
  switch (cadence.toLowerCase()) {
    case 'daily':
      return Math.round((days * 252) / 365.25);
    case 'weekly':
      return Math.floor(days / 7);
    case 'monthly': {
      const a = new Date(start);
      const b = new Date(end);
      return (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth());
    }
    case 'quarterly': {
      const a = new Date(start);
      const b = new Date(end);
      return Math.floor(((b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth())) / 3);
    }
    default:
      return null;
  }
}

/** Percent from 0 to 100, clamped, for a progress bar. */
export function progressFraction(percent: number): number {
  if (!Number.isFinite(percent)) return 0;
  return Math.max(0, Math.min(1, percent / 100));
}

export interface RunListItem {
  id: string;
  strategyId: string;
  name: string;
  version: number;
  at: number;
  ret: number | null;
  sharpe: number | null;
  state: 'completed' | 'running' | 'failed' | 'cancelled' | 'pending';
}

/** The newest completed run, and every other run newest first; running ones are kept apart. */
export function splitRuns(runs: readonly RunListItem[]): { running: RunListItem[]; latest: RunListItem | null; earlier: RunListItem[] } {
  const sorted = [...runs].sort((a, b) => b.at - a.at);
  const running = sorted.filter((r) => r.state === 'running' || r.state === 'pending');
  const done = sorted.filter((r) => r.state !== 'running' && r.state !== 'pending');
  const latestIdx = done.findIndex((r) => r.state === 'completed');
  const latest = latestIdx >= 0 ? done[latestIdx] : null;
  return { running, latest, earlier: done.filter((_, i) => i !== latestIdx) };
}

/** "Recession Radar v3". */
export function runTitle(name: string, version: number): string {
  return version > 0 ? `${name} v${version}` : name;
}

export interface Lane {
  symbol: string;
  /** Fractions of the run's width. */
  spans: { from: number; to: number }[];
}

export interface HeldSpan {
  symbol: string;
  from: number;
  to: number;
}

/** One lane per symbol, the longest-held first, with spans placed on 0..1 across the run. */
export function lanesOf(spans: readonly HeldSpan[], start: number, end: number, max = 4): Lane[] {
  if (end <= start) return [];
  const bySym = new Map<string, { from: number; to: number }[]>();
  for (const s of spans) {
    const from = Math.max(0, (s.from - start) / (end - start));
    const to = Math.min(1, (s.to - start) / (end - start));
    if (to <= from) continue;
    const list = bySym.get(s.symbol) ?? [];
    list.push({ from, to });
    bySym.set(s.symbol, list);
  }
  const total = (l: { from: number; to: number }[]) => l.reduce((t, x) => t + x.to - x.from, 0);
  return [...bySym.entries()]
    .map(([symbol, list]) => ({ symbol, spans: list.sort((a, b) => a.from - b.from) }))
    .sort((a, b) => total(b.spans) - total(a.spans))
    .slice(0, max);
}
