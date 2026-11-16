/** Full-width background charts behind the hero and each section, one market shape per section. */

import { mulberry } from '../../lib/illustrative/random';

import { candle, clamp, r1, type Shape, type ShapeGroup } from './shapes';

type ChartKind = 'candles' | 'equity' | 'steps' | 'line';

export interface ChartShape {
  kind: ChartKind;
  seed: number;
  /** The underlying trend, 0 to 1 (1 at the top), over t from 0 to 1. */
  path: (t: number) => number;
  /** Dotted price levels, as positions on the same 0 to 1 scale. */
  levels: readonly number[];
  /** Price the level labels are drawn around. */
  base: number;
  /** Wider spacing and thinner bodies. */
  sparse?: boolean;
}

export const SECTION_SHAPES = {
  top: {
    kind: 'candles',
    seed: 4242,
    path: (t) => 0.22 + t * 0.66 + Math.sin(t * 14) * 0.03 + Math.sin(t * 5.7) * 0.04,
    levels: [0.78, 0.5],
    base: 612.5,
  },
  build: {
    kind: 'candles',
    seed: 5101,
    path: (t) => 0.5 + Math.sin(t * 8) * 0.26 + Math.sin(t * 21) * 0.07,
    levels: [0.66, 0.34],
    base: 418.2,
  },
  backtest: {
    kind: 'equity',
    seed: 6203,
    path: (t) =>
      0.2 +
      t * 0.62 +
      Math.sin(t * 13) * 0.05 -
      (t > 0.42 && t < 0.58 ? Math.sin(((t - 0.42) / 0.16) * Math.PI) * 0.16 : 0),
    levels: [0.75, 0.45],
    base: 25000,
  },
  copilot: {
    kind: 'candles',
    seed: 7307,
    path: (t) => 0.85 - 3.1 * t * (1 - t) + t * 0.05 + Math.sin(t * 17) * 0.03,
    levels: [0.25],
    base: 182.4,
  },
  live: {
    kind: 'steps',
    seed: 8411,
    path: (t) => 0.3 + t * 0.45 + Math.sin(t * 11) * 0.06,
    levels: [0.75, 0.45],
    base: 103410,
  },
  own: {
    kind: 'candles',
    seed: 9513,
    path: (t) => 0.12 + t * 0.72 + Math.sin(t * 7) * 0.09,
    levels: [0.72, 0.48],
    base: 612.5,
    sparse: true,
  },
  join: {
    kind: 'line',
    seed: 1619,
    path: (t) => 0.12 + Math.pow(t, 1.5) * 0.78 + Math.sin(t * 15) * 0.03,
    levels: [0.75, 0.45],
    base: 682.15,
  },
} satisfies Record<string, ChartShape>;

export type SectionArtId = keyof typeof SECTION_SHAPES;

export interface ChartBox {
  width: number;
  /** Top of the price band. */
  top: number;
  /** Height of the price band; volume and markers sit just below it. */
  height: number;
}

/** Dollar amounts for large bases, plain prices otherwise. */
export function levelLabel(price: number, base: number): string {
  return base >= 10000 ? `$${Math.round(price).toLocaleString('en-US')}` : price.toFixed(2);
}

/**
 * The ink layers (body, volume and levels) and the accent layer (moving average or curve). Ink
 * groups carry `sa`, the drawn body `sa sabody`, the accent `sa acc`; strokes that draw in set
 * `draw`.
 */
export function chartArt(shape: ChartShape, box: ChartBox): ShapeGroup[] {
  const { width: W, top, height: ht } = box;
  if (W <= 0 || ht <= 0) return [];
  const r = mulberry(shape.seed);
  const y = (v: number) => top + (1 - v) * ht;
  const val = (t: number) => clamp(shape.path(t), 0.04, 0.96);
  const body: Shape[] = [];
  const accent: Shape[] = [];

  if (shape.kind === 'candles') {
    const n = Math.max(
      36,
      Math.min(shape.sparse ? 80 : 120, Math.floor(W / (shape.sparse ? 16 : 12)))
    );
    const sp = W / n;
    const bw = Math.max(2, sp * (shape.sparse ? 0.42 : 0.55));
    const closes: [number, number][] = [];
    const volume: Shape[] = [];
    let prev = val(0);
    for (let i = 0; i < n; i++) {
      const open = prev;
      const close = clamp(val((i + 1) / n) + (r() - 0.5) * 0.06, 0.03, 0.97);
      const high = Math.min(0.99, Math.max(open, close) + r() * 0.035);
      const low = Math.max(0.01, Math.min(open, close) - r() * 0.035);
      const cx = i * sp + sp / 2;
      body.push(...candle(cx, bw, open, close, high, low, y));
      const vh = 5 + r() * 30 * (0.5 + Math.abs(close - open) * 8);
      volume.push({
        kind: 'rect',
        x: r1(cx - bw / 2),
        y: r1(top + ht + 66 - vh),
        w: r1(bw),
        h: r1(vh),
        fill: 'tint',
        opacity: 0.6,
      });
      closes.push([cx, close]);
      prev = close;
    }
    body.push(...volume);
    const ma = closes
      .map(([cx], i) => {
        const win = closes.slice(Math.max(0, i - 8), i + 1);
        const avg = win.reduce((s, c) => s + c[1], 0) / win.length;
        return `${i ? 'L' : 'M'}${r1(cx)},${r1(y(avg))}`;
      })
      .join('');
    accent.push({ kind: 'path', d: ma, width: 1.6, draw: true });
  } else {
    const steps = 160;
    const pts: [number, number][] = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      pts.push([t * W, clamp(val(t) + (r() - 0.5) * 0.02, 0.03, 0.97)]);
    }
    const line = pts.map(([x, v], i) => `${i ? 'L' : 'M'}${r1(x)},${r1(y(v))}`).join('');

    if (shape.kind === 'steps') {
      let d = '';
      let held = pts[0][1];
      d = `M0,${r1(y(held))}`;
      const marks: number[] = [];
      pts.forEach(([x, v], i) => {
        if (i > 0 && i % 16 === 0 && v !== held) {
          d += ` H${r1(x)} V${r1(y(v))}`;
          marks.push(x);
          held = v;
        }
      });
      d += ` H${r1(W)}`;
      accent.push({ kind: 'path', d, width: 1.6, draw: true });
      const base = top + ht + 24;
      for (const x of marks)
        body.push({ kind: 'line', x1: r1(x), x2: r1(x), y1: r1(base - 6), y2: r1(base + 6) });
      body.push({ kind: 'line', x1: 0, x2: r1(W), y1: r1(base), y2: r1(base), width: 0.6 });
      body.push({ kind: 'path', d: line, dash: '2 3' });
    } else {
      accent.push(
        {
          kind: 'path',
          d: `${line} L${r1(W)},${r1(top + ht)} L0,${r1(top + ht)} Z`,
          fill: 'gradient',
          opacity: 0.5,
        },
        { kind: 'path', d: line, width: 1.6, draw: true }
      );
      if (shape.kind === 'equity') {
        const base = top + ht + 30;
        let peak = 0;
        let dd = `M0,${r1(base)}`;
        for (const [x, v] of pts) {
          peak = Math.max(peak, v);
          dd += ` L${r1(x)},${r1(base + (peak - v) * 260)}`;
        }
        body.push(
          { kind: 'line', x1: 0, x2: r1(W), y1: r1(base), y2: r1(base) },
          { kind: 'path', d: `${dd} L${r1(W)},${r1(base)} Z`, fill: 'tint', opacity: 0.45 }
        );
      } else {
        const bars = Math.floor(W / 11);
        for (let i = 0; i < bars; i++) {
          const bh = 6 + r() * 30 * (0.4 + i / bars);
          body.push({
            kind: 'rect',
            x: i * 11,
            y: r1(top + ht + 70 - bh),
            w: 6,
            h: r1(bh),
            fill: 'tint',
            opacity: 1,
          });
        }
      }
    }
  }

  const levels: Shape[] = [];
  for (const v of shape.levels) {
    const yy = r1(y(v));
    levels.push(
      { kind: 'line', x1: 0, x2: r1(W - 64), y1: yy, y2: yy, dash: '2 4' },
      {
        kind: 'text',
        x: r1(W - 8),
        y: r1(yy + 3.5),
        text: levelLabel(shape.base * (1 + (v - 0.5) * 0.06), shape.base),
        anchor: 'end',
        size: 10,
      }
    );
  }

  return [
    { paint: 'ink', className: 'sa sabody', shapes: body },
    { paint: 'ink', className: 'sa', shapes: levels },
    { paint: 'accent', className: 'sa acc', shapes: accent },
  ];
}

/** The price band for a section whose heading is centred at `headY`. */
export function sectionBox(width: number, sectionHeight: number, headY: number) {
  const height = Math.min(sectionHeight, headY + 460);
  const top = Math.max(24, headY - 200);
  return { height, box: { width, top, height: Math.min(400, height * 0.62) } };
}
