import { useMemo, useState, type ReactNode } from 'react';

import {
  areaPath,
  linePath,
  nearestIndex,
  xAt,
  xTickIndexes,
  yAt,
  yDomain,
  yTicks,
  type Padding,
  type Plot,
} from '../../lib/chart/scale';

import { useWidth } from './useWidth';

/** main: the accent line; bench: a dashed recessive line; loss: drawdown in the loss colour. */
export type SeriesKind = 'main' | 'bench' | 'loss';

export interface ChartSeries {
  values: readonly number[];
  kind: SeriesKind;
  area?: boolean;
  label?: string;
}

export interface LineChartProps {
  /** One date per point, shared by every series. */
  dates: readonly Date[];
  series: readonly ChartSeries[];
  height?: number;
  yFormat?: (v: number) => string;
  xFormat?: (d: Date) => string;
  yTickCount?: number;
  xTickCount?: number;
  /** Fixed bottom of the y domain and of any area. */
  base?: number;
  ceil?: number;
  zeroLine?: number;
  tooltip?: (i: number) => ReactNode;
  pad?: Partial<Padding>;
  label: string;
  className?: string;
}

const STROKE: Record<SeriesKind, { stroke: string; width: number; dash?: string }> = {
  main: { stroke: 'rgb(var(--accent))', width: 1.5 },
  bench: { stroke: 'rgb(var(--fg-3))', width: 1, dash: '3 3' },
  loss: { stroke: 'rgb(var(--loss))', width: 1 },
};

const AREA: Record<SeriesKind, { fill: string; opacity: number }> = {
  main: { fill: 'rgb(var(--accent))', opacity: 0.09 },
  bench: { fill: 'rgb(var(--fg-3))', opacity: 0.06 },
  loss: { fill: 'rgb(var(--loss))', opacity: 0.16 },
};

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthYear = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;

/** One y-axis, a recessive dashed grid and a crosshair tooltip. */
export function LineChart({
  dates,
  series,
  height = 240,
  yFormat = (v) => v.toFixed(0),
  xFormat = monthYear,
  yTickCount = 4,
  xTickCount = 5,
  base,
  ceil,
  zeroLine,
  tooltip,
  pad,
  label,
  className = '',
}: LineChartProps) {
  const [ref, measured] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const width = Math.max(260, measured);
  const narrow = width < 480;
  const count = series[0]?.values.length ?? 0;

  const plot: Plot = useMemo(() => {
    const p = { t: 12, r: 12, b: 26, l: 56, ...pad };
    if (narrow) p.l = Math.min(p.l, 46);
    return {
      width,
      height,
      pad: p,
      domain: yDomain(
        series.map((s) => s.values),
        { base, ceil }
      ),
      count,
    };
  }, [width, height, pad, narrow, series, base, ceil, count]);

  const xIdx = xTickIndexes(count, narrow ? Math.min(3, xTickCount) : xTickCount);
  const areaBase = base ?? plot.domain.lo;

  // The hit rect starts at pad.l, so offset back into plot coordinates.
  const onMove = (clientX: number, hit: DOMRect) =>
    setHover(nearestIndex(plot, clientX - hit.left + plot.pad.l));

  return (
    <div ref={ref} className={`relative w-full ${className}`}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={label}
        className="block overflow-visible"
      >
        <g>
          {yTicks(plot.domain, yTickCount).map((v) => {
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
                  {yFormat(v)}
                </text>
              </g>
            );
          })}
        </g>
        {zeroLine !== undefined && (
          <line
            x1={plot.pad.l}
            x2={width - plot.pad.r}
            y1={Math.round(yAt(plot, zeroLine)) + 0.5}
            y2={Math.round(yAt(plot, zeroLine)) + 0.5}
            stroke="rgb(var(--line-strong))"
          />
        )}
        {xIdx.map((i, k) => (
          <text
            key={i}
            x={xAt(plot, i)}
            y={height - 6}
            textAnchor={k === 0 ? 'start' : k === xIdx.length - 1 ? 'end' : 'middle'}
            className="fill-fg-3 font-mono text-[10px]"
          >
            {dates[i] ? xFormat(dates[i]) : ''}
          </text>
        ))}
        {series.map((s, k) => (
          <g key={k}>
            {s.area && (
              <path
                d={areaPath(plot, s.values, areaBase)}
                fill={AREA[s.kind].fill}
                opacity={AREA[s.kind].opacity}
              />
            )}
            <path
              d={linePath(plot, s.values)}
              fill="none"
              stroke={STROKE[s.kind].stroke}
              strokeWidth={STROKE[s.kind].width}
              strokeDasharray={STROKE[s.kind].dash}
              strokeLinejoin="round"
            />
          </g>
        ))}
        {hover !== null && (
          <g>
            <line
              x1={xAt(plot, hover)}
              x2={xAt(plot, hover)}
              y1={plot.pad.t}
              y2={height - plot.pad.b}
              stroke="rgb(var(--fg-3))"
              strokeDasharray="2 3"
            />
            {series.map((s, k) => (
              <circle
                key={k}
                cx={xAt(plot, hover)}
                cy={yAt(plot, s.values[hover])}
                r={4}
                fill={STROKE[s.kind].stroke}
                stroke="rgb(var(--panel))"
                strokeWidth={2}
              />
            ))}
          </g>
        )}
        <rect
          x={plot.pad.l}
          y={0}
          width={Math.max(0, width - plot.pad.l - plot.pad.r)}
          height={height}
          fill="transparent"
          onMouseMove={(e) => onMove(e.clientX, e.currentTarget.getBoundingClientRect())}
          onTouchMove={(e) => onMove(e.touches[0].clientX, e.currentTarget.getBoundingClientRect())}
          onMouseLeave={() => setHover(null)}
          onTouchEnd={() => setHover(null)}
        />
      </svg>
      {hover !== null && tooltip && (
        <Tip x={xAt(plot, hover)} top={plot.pad.t + 4} width={width}>
          {tooltip(hover)}
        </Tip>
      )}
    </div>
  );
}

function Tip({
  x,
  top,
  width,
  children,
}: {
  x: number;
  top: number;
  width: number;
  children: ReactNode;
}) {
  const flip = x + 14 + 180 > width;
  return (
    <div
      className="pointer-events-none absolute z-10 whitespace-nowrap rounded border border-line-strong bg-panel px-2 py-1.5 font-mono text-[11px] leading-normal text-fg shadow-lg"
      style={flip ? { right: width - x + 14, top } : { left: x + 14, top }}
    >
      {children}
    </div>
  );
}
