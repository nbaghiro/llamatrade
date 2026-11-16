/** Pure SVG path math for the native charts; geometry only, no rendering. */

export interface Range {
  min: number;
  max: number;
}

/** Min and max across every finite value of every series, or null when there are none. */
export function rangeOf(...series: ReadonlyArray<readonly number[] | undefined>): Range | null {
  let min = Infinity;
  let max = -Infinity;
  for (const s of series) {
    for (const v of s ?? []) {
      if (!Number.isFinite(v)) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }
  return min <= max ? { min, max } : null;
}

/** y for a value inside a WxH box; a flat range sits in the middle. */
export function yFor(v: number, range: Range, h: number, pad = 3): number {
  const span = range.max - range.min;
  if (span === 0) return h / 2;
  return pad + (h - pad * 2) * (1 - (v - range.min) / span);
}

/** Polyline through the values, fit to a WxH box on a shared `range` (defaults to its own). */
export function linePath(values: readonly number[], w: number, h: number, pad = 3, range?: Range): string {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length < 2) return '';
  const r = range ?? rangeOf(finite);
  if (!r) return '';
  const stepX = (w - pad * 2) / (finite.length - 1);
  return finite
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(pad + i * stepX).toFixed(1)},${yFor(v, r, h, pad).toFixed(1)}`)
    .join(' ');
}

/** Closed area under the polyline, for the fill. */
export function areaPath(values: readonly number[], w: number, h: number, pad = 3, range?: Range): string {
  const line = linePath(values, w, h, pad, range);
  if (!line) return '';
  return `${line} L${(w - pad).toFixed(1)},${h} L${pad.toFixed(1)},${h} Z`;
}

/** Compact axis figure: 104.2k, 1.3M, 950. */
export function axisLabel(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}k`;
  return `${sign}${abs.toFixed(abs >= 100 ? 0 : 1)}`;
}

/** Scales a series so it starts at `start`, for comparing a benchmark against equity. */
export function rebase(series: readonly number[], start: number): number[] {
  const first = series.find((v) => Number.isFinite(v) && v !== 0);
  if (first === undefined || !Number.isFinite(start) || start === 0) return [...series];
  return series.map((v) => (v * start) / first);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Labels for the first, evenly spaced middle and last of a run of Unix-second times:
 * "Oct 14" within a year, "Jul 2024" across more than one.
 */
export function timeLabels(times: readonly number[], count = 3): string[] {
  const valid = times.filter((t) => Number.isFinite(t) && t > 0);
  if (valid.length < 2 || count < 2) return [];
  const long = valid[valid.length - 1] - valid[0] > 330 * 86_400;
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(valid[Math.round(((valid.length - 1) * i) / (count - 1))] * 1000);
    return long ? `${MONTHS[d.getMonth()]} ${d.getFullYear()}` : `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  });
}
