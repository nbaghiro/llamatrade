/** Pure geometry for the SVG charts. */

export interface Padding {
  t: number;
  r: number;
  b: number;
  l: number;
}

export interface Domain {
  lo: number;
  hi: number;
}

export interface DomainOptions {
  /** Fixed lower bound (an area baseline); otherwise 6% headroom below the data. */
  base?: number;
  /** Fixed upper bound; otherwise 6% headroom above the data. */
  ceil?: number;
}

export function yDomain(
  series: ReadonlyArray<readonly number[]>,
  opts: DomainOptions = {}
): Domain {
  const all = series.flatMap((s) => s.filter(Number.isFinite));
  if (!all.length) return { lo: opts.base ?? 0, hi: opts.ceil ?? 1 };
  let lo = Math.min(...all, opts.base ?? Infinity);
  let hi = Math.max(...all, opts.ceil ?? -Infinity);
  const span = hi - lo || Math.abs(hi) || 1;
  if (opts.base === undefined) lo -= span * 0.06;
  if (opts.ceil === undefined) hi += span * 0.06;
  if (hi === lo) hi = lo + 1;
  return { lo, hi };
}

export interface Plot {
  width: number;
  height: number;
  pad: Padding;
  domain: Domain;
  count: number;
}

export function xAt(plot: Plot, i: number): number {
  const inner = plot.width - plot.pad.l - plot.pad.r;
  return plot.count <= 1 ? plot.pad.l + inner / 2 : plot.pad.l + (i / (plot.count - 1)) * inner;
}

export function yAt(plot: Plot, v: number): number {
  const { lo, hi } = plot.domain;
  return plot.pad.t + (1 - (v - lo) / (hi - lo)) * (plot.height - plot.pad.t - plot.pad.b);
}

export function linePath(plot: Plot, values: readonly number[]): string {
  return values
    .map((v, i) => `${i ? 'L' : 'M'}${xAt(plot, i).toFixed(1)},${yAt(plot, v).toFixed(1)}`)
    .join(' ');
}

export function areaPath(plot: Plot, values: readonly number[], baseline: number): string {
  if (!values.length) return '';
  const b = yAt(plot, baseline).toFixed(1);
  const first = xAt(plot, 0).toFixed(1);
  const last = xAt(plot, values.length - 1).toFixed(1);
  return `M${first},${b} L${linePath(plot, values).slice(1)} L${last},${b} Z`;
}

/** A round tick step (1, 2 or 5 times a power of ten) near span / count. */
export function niceStep(span: number, count: number): number {
  const raw = Math.abs(span) / Math.max(1, count);
  if (!Number.isFinite(raw) || raw <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(raw));
  const err = raw / power;
  const factor = err >= Math.sqrt(50) ? 10 : err >= Math.sqrt(10) ? 5 : err >= Math.sqrt(2) ? 2 : 1;
  return factor * power;
}

/** Grid values at round steps inside the domain, about `count` intervals apart. */
export function yTicks(domain: Domain, count: number): number[] {
  const { lo, hi } = domain;
  const step = niceStep(hi - lo, count);
  const first = Math.ceil(lo / step - 1e-9);
  const last = Math.floor(hi / step + 1e-9);
  if (last < first) return [lo, hi];
  const out: number[] = [];
  for (let k = first; k <= last; k++) out.push(Number((k * step).toPrecision(12)));
  return out;
}

/** Indexes for x-axis labels, first and last included, without duplicates. */
export function xTickIndexes(count: number, ticks: number): number[] {
  if (count <= 0) return [];
  const n = Math.max(1, Math.min(ticks, count - 1));
  const out = new Set<number>();
  for (let k = 0; k <= n; k++) out.add(Math.round(((count - 1) * k) / n));
  return [...out];
}

/** The data index closest to a pointer x position. */
export function nearestIndex(plot: Plot, px: number): number {
  if (plot.count <= 1) return 0;
  const inner = plot.width - plot.pad.l - plot.pad.r;
  const i = Math.round(((px - plot.pad.l) / inner) * (plot.count - 1));
  return Math.max(0, Math.min(plot.count - 1, i));
}
