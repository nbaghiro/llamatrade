import type { ConditionStats } from '@llamatrade/core/strategy/indicators';
import { useMemo, useRef, type PointerEvent as ReactPointerEvent } from 'react';

import { useWidth } from '../../charts/useWidth';

import { fmt, monthYear, type RebalanceEvery } from './conditionHistory';

export const CHART_H = 200;
const PAD_R = 52;

export interface History {
  dates: Date[];
  values: number[];
  lastClose: number | null;
}

interface ChartProps {
  history: History;
  threshold: number;
  saved: number | null;
  savedLabel: string;
  stats: ConditionStats;
  savedStats: ConditionStats | null;
  rebalances: number[];
  every: RebalanceEvery;
  onDrag: (value: number) => void;
  onRelease: () => void;
}

export function ThresholdChart({
  history,
  threshold,
  saved,
  savedLabel,
  stats,
  savedStats,
  rebalances,
  every,
  onDrag,
  onRelease,
}: ChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);
  const { dates, values } = history;
  const plotW = Math.max(120, width - PAD_R);
  const n = values.length;

  const [lo, hi] = useMemo(() => {
    const finite = values.filter(Number.isFinite);
    const all = [...finite, threshold, ...(saved !== null ? [saved] : [])];
    let min = Math.min(...all);
    let max = Math.max(...all);
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const pad = (max - min) * 0.08;
    return [min - pad, max + pad];
  }, [values, threshold, saved]);

  const x = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * plotW);
  const y = (v: number) => CHART_H - ((v - lo) / (hi - lo)) * CHART_H;
  const valueAt = (py: number) => lo + ((CHART_H - py) / CHART_H) * (hi - lo);

  const path = useMemo(() => {
    let d = '';
    let pen = false;
    values.forEach((v, i) => {
      if (!Number.isFinite(v)) {
        pen = false;
        return;
      }
      d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, plotW, lo, hi]);

  const heldAt = new Set(stats.rebalancesHeld);
  const savedHeldAt = new Set(savedStats?.rebalancesHeld ?? []);

  const move = (e: ReactPointerEvent<SVGElement>) => {
    if (!dragging.current || !svgRef.current) return;
    const box = svgRef.current.getBoundingClientRect();
    const py = Math.max(0, Math.min(CHART_H, e.clientY - box.top));
    onDrag(valueAt(py));
  };
  const end = () => {
    if (!dragging.current) return;
    dragging.current = false;
    onRelease();
  };

  const ty = y(threshold);
  const ticks = [lo + (hi - lo) * 0.25, lo + (hi - lo) * 0.6];

  return (
    <div ref={ref} className="min-w-0">
      <svg
        ref={svgRef}
        width={width}
        height={CHART_H}
        role="img"
        aria-label={`History with the threshold at ${fmt(threshold)}`}
        className="block touch-none select-none"
        onPointerMove={move}
        onPointerUp={end}
        onPointerLeave={end}
      >
        {stats.stretches.map((s) => (
          <rect
            key={s.from}
            x={x(s.from)}
            width={Math.max(1.5, x(s.to) - x(s.from))}
            y={0}
            height={CHART_H}
            fill="rgb(var(--accent) / 0.1)"
          />
        ))}
        {ticks.map((t) => (
          <text key={t} x={plotW + 10} y={y(t) + 4} className="fill-fg-3 font-mono text-[10.5px]">
            {fmt(t)}
          </text>
        ))}
        {saved !== null && saved !== threshold && (
          <>
            <line
              x1={0}
              x2={plotW}
              y1={y(saved)}
              y2={y(saved)}
              stroke="rgb(var(--fg-3))"
              strokeDasharray="4 3"
              strokeWidth={1}
            />
            <text
              x={plotW + 6}
              y={y(saved) + (y(saved) > ty ? 14 : -6)}
              className="fill-fg-3 font-mono text-[10.5px]"
            >
              {fmt(saved)} · {savedLabel}
            </text>
          </>
        )}
        <path d={path} fill="none" stroke="rgb(var(--accent))" strokeWidth={1.4} />
        <line x1={0} x2={plotW} y1={ty} y2={ty} stroke="rgb(var(--fg))" strokeWidth={1.2} />
        <rect
          x={0}
          width={plotW}
          y={ty - 8}
          height={16}
          fill="transparent"
          className="cursor-ns-resize"
          onPointerDown={(e) => {
            dragging.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={move}
          onPointerUp={end}
        />
        <rect
          x={plotW / 2 - 13}
          y={ty - 5}
          width={26}
          height={10}
          rx={5}
          fill="rgb(var(--panel))"
          stroke="rgb(var(--fg))"
          className="pointer-events-none"
        />
        <rect x={plotW + 4} y={ty - 9} width={36} height={18} rx={3} fill="rgb(var(--fg))" />
        <text
          x={plotW + 22}
          y={ty + 4}
          textAnchor="middle"
          className="fill-canvas font-mono text-[11px] font-semibold"
        >
          {fmt(threshold)}
        </text>
      </svg>
      {every !== 'daily' && (
        <svg width={width} height={22} aria-hidden="true" className="mt-2 block">
          <line x1={0} x2={plotW} y1={11} y2={11} stroke="rgb(var(--line))" />
          {rebalances.map((i) =>
            heldAt.has(i) ? (
              <circle
                key={i}
                cx={x(i)}
                cy={11}
                r={4.5}
                fill="rgb(var(--canvas))"
                stroke="rgb(var(--accent))"
                strokeWidth={1.5}
              />
            ) : savedHeldAt.has(i) ? (
              <circle
                key={i}
                cx={x(i)}
                cy={11}
                r={4.5}
                fill="rgb(var(--canvas))"
                stroke="rgb(var(--fg-3))"
                strokeDasharray="2 2"
              />
            ) : (
              <line
                key={i}
                x1={x(i)}
                x2={x(i)}
                y1={5}
                y2={17}
                stroke="rgb(var(--accent) / 0.75)"
                strokeWidth={1.5}
              />
            )
          )}
        </svg>
      )}
      {n > 0 && (
        <div
          className="mt-1 flex justify-between font-mono text-[11px] text-fg-3"
          style={{ width: plotW }}
        >
          <span>{monthYear(dates[0])}</span>
          <span className="hidden sm:inline">{monthYear(dates[Math.floor((n - 1) / 2)])}</span>
          <span>{monthYear(dates[n - 1])}</span>
        </div>
      )}
    </div>
  );
}
