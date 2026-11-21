/** Time-based chart geometry shared by AnnotatedCurve and Lanes: pure, no rendering. */

import { rangeOf, type Range } from './paths.ts';

/** One value at a time, in epoch milliseconds. */
export interface TimePoint {
  t: number;
  v: number;
}

export interface TimeRange {
  from: number;
  until: number;
}

const DAY = 86_400_000;

/** x for a time inside a plot that runs from `left` to `left + width`; clamped to the plot. */
export function xAt(t: number, range: TimeRange, width: number, left = 0): number {
  const span = range.until - range.from;
  if (!(span > 0)) return left + width;
  const k = (t - range.from) / span;
  return left + Math.max(0, Math.min(1, k)) * width;
}

/** The earliest and latest time across the series, or null when there are none. */
export function timeRangeOf(...series: ReadonlyArray<readonly TimePoint[] | undefined>): TimeRange | null {
  let from = Infinity;
  let until = -Infinity;
  for (const s of series) {
    for (const p of s ?? []) {
      if (!Number.isFinite(p.t)) continue;
      if (p.t < from) from = p.t;
      if (p.t > until) until = p.t;
    }
  }
  return from <= until ? { from, until } : null;
}

/** Value range across point series, ignoring non-finite values. */
export function valueRangeOf(...series: ReadonlyArray<readonly TimePoint[] | undefined>): Range | null {
  return rangeOf(...series.map((s) => s?.map((p) => p.v)));
}

function yIn(v: number, r: Range, h: number, pad: number): number {
  const span = r.max - r.min;
  if (span === 0) return h / 2;
  return pad + (h - pad * 2) * (1 - (v - r.min) / span);
}

/** Points inside the time range, in time order, dropping non-finite ones. */
export function clip(points: readonly TimePoint[], range: TimeRange): TimePoint[] {
  return points
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v) && p.t >= range.from && p.t <= range.until)
    .sort((a, b) => a.t - b.t);
}

/** Polyline through points placed by time; empty when fewer than two points fall in range. */
export function timeLinePath(
  points: readonly TimePoint[],
  range: TimeRange,
  values: Range,
  width: number,
  height: number,
  opts: { left?: number; pad?: number } = {},
): string {
  const left = opts.left ?? 0;
  const pad = opts.pad ?? 4;
  const shown = clip(points, range);
  if (shown.length < 2) return '';
  return shown
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(p.t, range, width, left).toFixed(1)},${yIn(p.v, values, height, pad).toFixed(1)}`)
    .join(' ');
}

/** The area under `timeLinePath`, closed along the bottom edge. */
export function timeAreaPath(
  points: readonly TimePoint[],
  range: TimeRange,
  values: Range,
  width: number,
  height: number,
  opts: { left?: number; pad?: number } = {},
): string {
  const line = timeLinePath(points, range, values, width, height, opts);
  if (!line) return '';
  const shown = clip(points, range);
  const left = opts.left ?? 0;
  const x0 = xAt(shown[0].t, range, width, left);
  const x1 = xAt(shown[shown.length - 1].t, range, width, left);
  return `${line} L${x1.toFixed(1)},${height} L${x0.toFixed(1)},${height} Z`;
}

/**
 * A step line: each value holds flat until the next point, then jumps. Used for money added,
 * where a deposit is a jump on its date rather than a slope. Extends to `range.until`.
 */
export function stepPath(
  points: readonly TimePoint[],
  range: TimeRange,
  values: Range,
  width: number,
  height: number,
  opts: { left?: number; pad?: number } = {},
): string {
  const left = opts.left ?? 0;
  const pad = opts.pad ?? 4;
  const sorted = points.filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v)).sort((a, b) => a.t - b.t);
  if (sorted.length === 0) return '';
  let carried: TimePoint | null = null;
  const inside: TimePoint[] = [];
  for (const p of sorted) {
    if (p.t < range.from) carried = p;
    else if (p.t <= range.until) inside.push(p);
  }
  const start = carried ? [{ t: range.from, v: carried.v }] : [];
  const pts = [...start, ...inside];
  if (pts.length === 0) return '';
  let d = '';
  pts.forEach((p, i) => {
    const x = xAt(p.t, range, width, left).toFixed(1);
    const y = yIn(p.v, values, height, pad).toFixed(1);
    d += i === 0 ? `M${x},${y}` : ` H${x} V${y}`;
  });
  d += ` H${xAt(range.until, range, width, left).toFixed(1)}`;
  return d;
}

/** y for one value, exposed for pins and the Now dot. */
export function yAt(v: number, values: Range, height: number, pad = 4): number {
  return yIn(v, values, height, pad);
}

/** The value of a series at time t: the last point at or before it, else null. */
export function valueAt(points: readonly TimePoint[], t: number): number | null {
  let out: number | null = null;
  let best = -Infinity;
  for (const p of points) {
    if (p.t <= t && p.t >= best && Number.isFinite(p.v)) {
      best = p.t;
      out = p.v;
    }
  }
  return out;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Nov 17" for spans under a year, "Nov 2025" for longer ones. */
export function tickLabel(t: number, span: number): string {
  const d = new Date(t);
  return span > 330 * DAY ? `${MONTHS[d.getMonth()]} ${d.getFullYear()}` : `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

/** Evenly spaced date labels across a range, first and last included. */
export function dateTicks(range: TimeRange, count = 3): { t: number; label: string }[] {
  const span = range.until - range.from;
  if (!(span > 0) || count < 2) return [];
  return Array.from({ length: count }, (_, i) => {
    const t = range.from + (span * i) / (count - 1);
    return { t, label: tickLabel(t, span) };
  });
}

/** Two-letter code for a lane label: "All-Weather Portfolio" as "AW". */
export function laneCode(name: string): string {
  const words = name
    .replace(/\(.*?\)/g, ' ')
    .split(/[\s\-_/]+/)
    .filter((w) => /[a-z0-9]/i.test(w));
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** Widths for bar segments across a width with a gap between each; non-positive values get 0. */
export function splitWidths(values: readonly number[], width: number, gap = 3): number[] {
  const shown = values.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const total = shown.reduce((a, b) => a + b, 0);
  const count = shown.filter((v) => v > 0).length;
  const room = Math.max(0, width - gap * Math.max(0, count - 1));
  if (total <= 0) return shown.map(() => 0);
  return shown.map((v) => (v / total) * room);
}
