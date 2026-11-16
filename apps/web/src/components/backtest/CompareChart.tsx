import { useMemo, useState } from 'react';

import {
  linePath,
  nearestIndex,
  xAt,
  xTickIndexes,
  yAt,
  yDomain,
  yTicks,
  type Plot,
} from '../../lib/chart/scale';
import { formatPct } from '../../lib/format';
import { useWidth } from '../charts/useWidth';

import { compareColor } from './compareColors';

export interface CompareLine {
  label: string;
  /** Growth of 1 on the shared dates. */
  values: readonly number[];
  bench?: boolean;
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Several runs on one axis, as cumulative return from the shared start. */
export function CompareChart({
  dates,
  lines,
  height = 300,
}: {
  dates: readonly Date[];
  lines: readonly CompareLine[];
  height?: number;
}) {
  const [ref, measured] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const width = Math.max(260, measured);
  const narrow = width < 480;
  const plot: Plot = useMemo(
    () => ({
      width,
      height,
      pad: { t: 12, r: 12, b: 26, l: narrow ? 46 : 56 },
      domain: yDomain(lines.map((l) => l.values)),
      count: dates.length,
    }),
    [width, height, narrow, lines, dates.length]
  );
  const runIndex = (k: number) => lines.slice(0, k).filter((l) => !l.bench).length;
  const strokeOf = (l: CompareLine, k: number) =>
    l.bench ? 'rgb(var(--fg-3))' : compareColor(runIndex(k));
  const xIdx = xTickIndexes(dates.length, narrow ? 3 : 5);

  return (
    <div ref={ref} className="relative w-full">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Cumulative return of ${lines.map((l) => l.label).join(', ')}`}
        className="block overflow-visible"
      >
        {yTicks(plot.domain, 4).map((v) => {
          const y = Math.round(yAt(plot, v)) + 0.5;
          return (
            <g key={v}>
              <line
                x1={plot.pad.l}
                x2={width - plot.pad.r}
                y1={y}
                y2={y}
                stroke="rgb(var(--grid))"
                strokeDasharray="var(--grid-dash)"
              />
              <text
                x={plot.pad.l - 8}
                y={y + 4}
                textAnchor="end"
                className="fill-fg-3 font-mono text-[10px]"
              >
                {formatPct(v - 1, { dp: 0, signed: true })}
              </text>
            </g>
          );
        })}
        {xIdx.map((i, k) => (
          <text
            key={i}
            x={xAt(plot, i)}
            y={height - 6}
            textAnchor={k === 0 ? 'start' : k === xIdx.length - 1 ? 'end' : 'middle'}
            className="fill-fg-3 font-mono text-[10px]"
          >
            {dates[i] ? `${MON[dates[i].getUTCMonth()]} ${dates[i].getUTCFullYear()}` : ''}
          </text>
        ))}
        {lines.map((l, k) => (
          <path
            key={l.label}
            d={linePath(plot, l.values)}
            fill="none"
            stroke={strokeOf(l, k)}
            strokeWidth={l.bench ? 1 : k === 0 ? 1.6 : 1.3}
            strokeDasharray={l.bench ? '3 3' : undefined}
            strokeLinejoin="round"
          />
        ))}
        {hover !== null && (
          <line
            x1={xAt(plot, hover)}
            x2={xAt(plot, hover)}
            y1={plot.pad.t}
            y2={height - plot.pad.b}
            stroke="rgb(var(--fg-3))"
            strokeDasharray="2 3"
          />
        )}
        <rect
          x={plot.pad.l}
          y={0}
          width={Math.max(0, width - plot.pad.l - plot.pad.r)}
          height={height}
          fill="transparent"
          onMouseMove={(e) =>
            setHover(
              nearestIndex(
                plot,
                e.clientX - e.currentTarget.getBoundingClientRect().left + plot.pad.l
              )
            )
          }
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute z-10 whitespace-nowrap rounded border border-line-strong bg-panel px-2 py-1.5 font-mono text-[11px] text-fg shadow-lg"
          style={
            xAt(plot, hover) + 200 > width
              ? { right: width - xAt(plot, hover) + 14, top: 16 }
              : { left: xAt(plot, hover) + 14, top: 16 }
          }
        >
          <b className="block font-medium text-fg-3">{dates[hover]?.toISOString().slice(0, 10)}</b>
          {lines.map((l, k) => (
            <span key={l.label} className="flex items-center gap-1.5">
              <i
                className="h-0.5 w-2.5"
                style={{ background: strokeOf(l, k) }}
                aria-hidden="true"
              />
              {l.label} {formatPct(l.values[hover] - 1, { dp: 1, signed: true })}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
