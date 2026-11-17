/** Time-based geometry for charts whose marks sit on dates rather than indexes. */

import type { Domain } from './scale';

const DAY_MS = 86_400_000;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Where `t` falls between `start` and `end`, from 0 to 1, clamped. */
export function timeFraction(t: Date, start: Date, end: Date): number {
  const span = end.getTime() - start.getTime();
  if (span <= 0) return 1;
  return Math.min(1, Math.max(0, (t.getTime() - start.getTime()) / span));
}

/** Percentage string for CSS `left`, e.g. "42.5%". */
export function pctAt(t: Date, start: Date, end: Date): string {
  return `${(timeFraction(t, start, end) * 100).toFixed(3)}%`;
}

/** True when `t` lies inside [start, end]. */
export function within(t: Date, start: Date, end: Date): boolean {
  return t.getTime() >= start.getTime() && t.getTime() <= end.getTime();
}

/**
 * The SVG path of `values` on dates, in a `width` by `height` box. Points outside the window
 * are dropped, and non-finite values break the line.
 */
export function timePath(
  dates: readonly Date[],
  values: readonly number[],
  start: Date,
  end: Date,
  domain: Domain,
  width: number,
  height: number
): string {
  const span = domain.hi - domain.lo || 1;
  let out = '';
  let pen = false;
  const n = Math.min(dates.length, values.length);
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (!Number.isFinite(v) || !within(dates[i], start, end)) {
      pen = false;
      continue;
    }
    const x = timeFraction(dates[i], start, end) * width;
    const y = (1 - (v - domain.lo) / span) * height;
    out += `${pen ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)} `;
    pen = true;
  }
  return out.trim();
}

/** The area under a time path, closed down to the bottom of the box; empty when the line breaks. */
export function timeArea(
  dates: readonly Date[],
  values: readonly number[],
  start: Date,
  end: Date,
  domain: Domain,
  width: number,
  height: number
): string {
  const line = timePath(dates, values, start, end, domain, width, height);
  if (!line || line.includes(' M')) return '';
  const coords = line.split(' ').map((seg) => seg.slice(1).split(',')[0]);
  const first = coords[0];
  const last = coords[coords.length - 1];
  return `M${first},${height} L${line.slice(1)} L${last},${height} Z`;
}

/** Index of the date nearest `t`; -1 when there are none. */
export function nearestDateIndex(dates: readonly Date[], t: Date): number {
  let best = -1;
  let gap = Infinity;
  for (let i = 0; i < dates.length; i++) {
    const g = Math.abs(dates[i].getTime() - t.getTime());
    if (g < gap) {
      gap = g;
      best = i;
    }
  }
  return best;
}

/** Month starts inside the window, thinned evenly to at most `max`. */
export function monthTicks(start: Date, end: Date, max = 5): Date[] {
  if (end.getTime() <= start.getTime()) return [];
  const spanDays = (end.getTime() - start.getTime()) / DAY_MS;
  const stepMonths = spanDays > 900 ? 12 : 1;
  const out: Date[] = [];
  let y = start.getUTCFullYear();
  let m = start.getUTCMonth();
  if (stepMonths === 12) m = 0;
  for (let k = 0; k < 600; k++) {
    const d = new Date(Date.UTC(y, m, 1));
    if (d.getTime() > end.getTime()) break;
    if (d.getTime() >= start.getTime()) out.push(d);
    m += stepMonths;
    if (m > 11) {
      y += Math.floor(m / 12);
      m %= 12;
    }
  }
  if (out.length <= max) return out;
  const every = Math.ceil(out.length / max);
  return out.filter((_, i) => i % every === 0);
}

/** "Aug 17" for spans under about two and a half years, "2022" beyond. */
export function tickLabel(d: Date, spanDays: number): string {
  if (spanDays > 900) return String(d.getUTCFullYear());
  return `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

export type PinAlign = 'start' | 'center' | 'end';

/** Labels near an edge grow inward so they stay inside the chart. */
export function pinAlign(fraction: number): PinAlign {
  if (fraction >= 0.88) return 'end';
  if (fraction <= 0.08) return 'start';
  return 'center';
}
