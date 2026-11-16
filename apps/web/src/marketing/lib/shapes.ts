/** SVG primitives for the decorative art. Every shape paints in currentColor. */

export type Shape =
  | { kind: 'line'; x1: number; y1: number; x2: number; y2: number; width?: number; dash?: string }
  | {
      kind: 'rect';
      x: number;
      y: number;
      w: number;
      h: number;
      /** hollow: outline only; solid: filled and outlined; tint: filled at `opacity`. */
      fill: 'hollow' | 'solid' | 'tint';
      opacity?: number;
      rx?: number;
    }
  | {
      kind: 'path';
      d: string;
      /** none: a stroke; tint: filled at `opacity`; gradient: the group's fade-down fill. */
      fill?: 'none' | 'tint' | 'gradient';
      opacity?: number;
      width?: number;
      dash?: string;
      /** Animates the stroke drawing in. */
      draw?: boolean;
    }
  | {
      kind: 'text';
      x: number;
      y: number;
      text: string;
      anchor: 'start' | 'middle' | 'end';
      size: number;
      italic?: boolean;
    };

export interface ShapeGroup {
  /** ink: the quiet art colour; accent: the accent. */
  paint: 'ink' | 'accent';
  shapes: Shape[];
  className?: string;
  opacity?: number;
}

export const r1 = (v: number) => Math.round(v * 10) / 10;

/** A polyline through `values` (0 to 1, 1 at the top) across the box. */
export function walkPath(values: readonly number[], x: number, y: number, w: number, h: number) {
  const last = Math.max(1, values.length - 1);
  return values
    .map((v, i) => `${i ? 'L' : 'M'}${r1(x + (i / last) * w)},${r1(y + (1 - v) * h)}`)
    .join('');
}

/** A bounded random walk between 0.05 and 0.95. */
export function walk(r: () => number, n: number, drift: number, vol: number): number[] {
  let v = 0.5;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    v = clamp(v + (r() - 0.5) * vol + drift, 0.05, 0.95);
    out.push(v);
  }
  return out;
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/** One candle: a wick and a body, hollow when it closes up. Values run 0 to 1 within the box. */
export function candle(
  cx: number,
  bodyWidth: number,
  open: number,
  close: number,
  high: number,
  low: number,
  y: (v: number) => number,
  minBody = 1.5
): Shape[] {
  const top = y(Math.max(open, close));
  const bottom = y(Math.min(open, close));
  return [
    { kind: 'line', x1: r1(cx), x2: r1(cx), y1: r1(y(high)), y2: r1(y(low)) },
    {
      kind: 'rect',
      x: r1(cx - bodyWidth / 2),
      y: r1(top),
      w: r1(bodyWidth),
      h: r1(Math.max(minBody, Math.abs(bottom - top))),
      fill: close >= open ? 'hollow' : 'solid',
    },
  ];
}
