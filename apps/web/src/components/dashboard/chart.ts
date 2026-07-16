// SVG path builders for the dashboard equity hero + strategy sparklines.

export interface CurvePoint {
  timestamp: string;
  value: number;
}

export interface BuiltPath {
  line: string;
  area: string;
  endX: number;
  endY: number;
}

const PERIOD_DAYS: Record<string, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
  ALL: null,
};

/** Trim a cumulative curve to the trailing window for a period (client-side). */
export function sliceByPeriod(points: CurvePoint[], period: string): CurvePoint[] {
  const days = PERIOD_DAYS[period];
  if (!days || points.length === 0) return points;
  const last = new Date(points[points.length - 1].timestamp).getTime();
  const cutoff = last - days * 86_400_000;
  const sliced = points.filter((p) => new Date(p.timestamp).getTime() >= cutoff);
  // A window with a single point cannot draw a line — fall back to the full curve.
  return sliced.length > 1 ? sliced : points;
}

/**
 * Project a value series into an SVG path over a `w`×`h` box. `min`/`max` set a
 * shared y-scale so multiple series (portfolio + benchmark) align. Returns empty
 * paths when there is nothing to draw.
 */
export function buildPath(
  values: number[],
  w: number,
  h: number,
  min: number,
  max: number
): BuiltPath {
  if (values.length < 2) return { line: '', area: '', endX: w, endY: h };
  const range = max - min || 1;
  const x = (i: number) => (i / (values.length - 1)) * w;
  const y = (v: number) => h - ((v - min) / range) * h;

  let line = `M${x(0).toFixed(2)},${y(values[0]).toFixed(2)}`;
  for (let i = 1; i < values.length; i++) {
    line += ` L${x(i).toFixed(2)},${y(values[i]).toFixed(2)}`;
  }
  const endX = x(values.length - 1);
  const endY = y(values[values.length - 1]);
  const area = `${line} L${endX.toFixed(2)},${h} L0,${h} Z`;
  return { line, area, endX, endY };
}

/** Min/max across several series, always including 0 so gains/losses read fairly. */
export function boundsOf(...series: number[][]): { min: number; max: number } {
  const all = series.flat();
  if (all.length === 0) return { min: -1, max: 1 };
  const min = Math.min(0, ...all);
  const max = Math.max(0, ...all);
  const pad = Math.max((max - min) * 0.08, 0.5);
  return { min: min - pad, max: max + pad };
}
