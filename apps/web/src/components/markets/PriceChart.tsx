import type { Candle } from '@llamatrade/core/stores/markets';
import { useMemo, useState } from 'react';

import { formatMoney } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { useWidth } from '../charts/useWidth';

export interface CostLine {
  price: number;
  label: string;
  live: boolean;
}

export interface FillMark {
  id: string;
  at: Date;
  price: number;
  side: 'buy' | 'sell';
  live: boolean;
  title: string;
}

interface PriceChartProps {
  label: string;
  candles: readonly Candle[];
  intraday: boolean;
  costLines?: readonly CostLine[];
  fills?: readonly FillMark[];
  height?: number;
  /** Name each average-cost line on the chart; off for small charts. */
  costLabels?: boolean;
}

const AXIS_W = 52;
const PAD_T = 10;
const PAD_B = 26;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function niceTicks(lo: number, hi: number, count = 4): number[] {
  const span = hi - lo;
  if (span <= 0) return [lo];
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}

/** The candle a moment falls in: the last one that opened at or before it. */
function candleIndex(candles: readonly Candle[], at: Date): number {
  const t = at.getTime() / 1000;
  if (candles.length === 0 || t < candles[0].time) return -1;
  let i = 0;
  while (i + 1 < candles.length && candles[i + 1].time <= t) i++;
  return i;
}

/**
 * A price chart with your own fills and each holding sleeve's average cost drawn on it. Daily
 * ranges draw candles; intraday ranges draw a line. Bars are spaced evenly, so closed days
 * leave no gaps.
 */
export function PriceChart({
  label,
  candles,
  intraday,
  costLines = [],
  fills = [],
  height = 340,
  costLabels = true,
}: PriceChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>(700);
  const [hover, setHover] = useState<number | null>(null);
  const plotW = Math.max(120, width - AXIS_W);
  const plotH = height - PAD_T - PAD_B;

  const domain = useMemo(() => {
    const prices = [
      ...candles.flatMap((c) => [c.low, c.high]),
      ...costLines.map((c) => c.price),
      ...fills.filter((f) => candleIndex(candles, f.at) >= 0).map((f) => f.price),
    ].filter((v) => Number.isFinite(v) && v > 0);
    if (prices.length === 0) return { lo: 0, hi: 1 };
    const lo = Math.min(...prices);
    const hi = Math.max(...prices);
    const pad = (hi - lo || hi * 0.02) * 0.08;
    return { lo: lo - pad, hi: hi + pad };
  }, [candles, costLines, fills]);

  const n = candles.length;
  const slot = n > 0 ? plotW / n : plotW;
  const x = (i: number) => (i + 0.5) * slot;
  const y = (v: number) => PAD_T + (1 - (v - domain.lo) / (domain.hi - domain.lo)) * plotH;
  const ticks = niceTicks(domain.lo, domain.hi);

  const xTicks = useMemo(() => {
    const out: { i: number; label: string }[] = [];
    let prevKey = '';
    candles.forEach((c, i) => {
      const d = new Date(c.time * 1000);
      const key = intraday ? String(d.getHours()) : `${d.getFullYear()}-${d.getMonth()}`;
      if (key !== prevKey && i > 0) {
        out.push({ i, label: intraday ? etClock(d) : MON[d.getMonth()] });
      }
      prevKey = key;
    });
    const every = Math.max(1, Math.ceil(out.length / Math.max(2, Math.floor(plotW / 90))));
    return out.filter((_, k) => k % every === 0);
  }, [candles, intraday, plotW]);

  const linePath = intraday
    ? candles.map((c, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(c.close).toFixed(1)}`).join('')
    : '';
  const bodyW = Math.max(1, Math.min(9, slot * 0.6));
  const hovered = hover !== null ? candles[hover] : null;

  return (
    <div ref={ref} className="relative w-full">
      {hovered && (
        <div className="pointer-events-none absolute left-1 top-0 z-10 rounded-[6px] border border-line bg-panel px-2 py-1 font-mono text-[11px] text-fg-2 shadow-sm">
          {new Date(hovered.time * 1000).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            ...(intraday ? { hour: 'numeric', minute: '2-digit' } : {}),
          })}{' '}
          · O {hovered.open.toFixed(2)} H {hovered.high.toFixed(2)} L {hovered.low.toFixed(2)} C{' '}
          {hovered.close.toFixed(2)}
        </div>
      )}
      <svg
        role="img"
        aria-label={label}
        width={width}
        height={height}
        className="block"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const i = Math.floor((e.clientX - box.left) / slot);
          setHover(i >= 0 && i < n ? i : null);
        }}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={0} x2={plotW} y1={y(v)} y2={y(v)} stroke="rgb(var(--line))" />
            <text x={plotW + 8} y={y(v) + 3.5} className="fill-fg-3 font-mono text-[10.5px]">
              {v >= 1000 ? v.toFixed(0) : v.toFixed(v < 10 ? 2 : 0)}
            </text>
          </g>
        ))}

        {intraday ? (
          <path d={linePath} fill="none" stroke="rgb(var(--accent))" strokeWidth={1.5} />
        ) : (
          candles.map((c, i) => {
            const up = c.close >= c.open;
            const top = y(Math.max(c.open, c.close));
            const bottom = y(Math.min(c.open, c.close));
            return (
              <g key={c.time} opacity={hover === null || hover === i ? 1 : 0.85}>
                <line x1={x(i)} x2={x(i)} y1={y(c.high)} y2={y(c.low)} stroke="rgb(var(--fg))" />
                <rect
                  x={x(i) - bodyW / 2}
                  y={top}
                  width={bodyW}
                  height={Math.max(1, bottom - top)}
                  fill={up ? 'rgb(var(--panel))' : 'rgb(var(--fg))'}
                  stroke="rgb(var(--fg))"
                />
              </g>
            );
          })
        )}

        {costLines.map((c) => (
          <g key={c.label}>
            <line
              x1={0}
              x2={plotW}
              y1={y(c.price)}
              y2={y(c.price)}
              stroke={c.live ? 'rgb(var(--fg))' : 'rgb(var(--accent))'}
              strokeDasharray={c.live ? undefined : '4 3'}
              strokeWidth={1.2}
            />
            {costLabels ? (
              <text x={8} y={y(c.price) - 5} className="fill-fg-2 font-mono text-[10.5px]">
                {c.label}
              </text>
            ) : (
              <title>{c.label}</title>
            )}
          </g>
        ))}

        {fills.map((f) => {
          const i = candleIndex(candles, f.at);
          if (i < 0) return null;
          const color = f.live ? 'rgb(var(--fg))' : 'rgb(var(--accent))';
          return (
            <g key={f.id}>
              <title>{f.title}</title>
              <circle
                cx={x(i)}
                cy={y(f.price)}
                r={7}
                fill={f.side === 'buy' ? color : 'rgb(var(--panel))'}
                stroke={color}
                strokeWidth={1.4}
              />
              <text
                x={x(i)}
                y={y(f.price) + 3}
                textAnchor="middle"
                className="font-mono text-[8.5px] font-semibold"
                fill={f.side === 'buy' ? 'rgb(var(--canvas))' : color}
              >
                {f.side === 'buy' ? 'B' : 'S'}
              </text>
            </g>
          );
        })}

        {hover !== null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={PAD_T}
            y2={PAD_T + plotH}
            stroke="rgb(var(--fg-3))"
            strokeDasharray="2 3"
          />
        )}

        {xTicks.map((t) => (
          <text
            key={t.i}
            x={x(t.i)}
            y={height - 8}
            textAnchor="middle"
            className="fill-fg-3 font-mono text-[10.5px]"
          >
            {t.label}
          </text>
        ))}
      </svg>
      <span className="sr-only">
        {candles.length
          ? `Last ${formatMoney(candles[candles.length - 1].close)}`
          : 'No prices in this range'}
      </span>
    </div>
  );
}
