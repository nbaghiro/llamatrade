import { useId, useMemo } from 'react';

import { yDomain } from '../../lib/chart/scale';
import { monthTicks, timeArea, timeFraction, timePath } from '../../lib/chart/timeScale';

const VIEW_W = 1000;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const tick = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;

interface MiniCurveProps {
  dates: readonly Date[];
  values: readonly number[];
  /** A dashed comparison on the same dates. */
  dashed?: readonly number[];
  /** Dates for the dashed line when they differ from `dates`. */
  dashedDates?: readonly Date[];
  height: number;
  /** accent for a session's money; muted for a backtest drawn on its own. */
  tone?: 'accent' | 'muted';
  /** Date labels under the curve: first, last and up to two between. */
  axis?: boolean;
  /** A dot at the last point. */
  endDot?: boolean;
  label: string;
}

/** A small equity curve on a time axis with an optional dashed comparison. */
export function MiniCurve({
  dates,
  values,
  dashed,
  dashedDates,
  height,
  tone = 'accent',
  axis = false,
  endDot = false,
  label,
}: MiniCurveProps) {
  const gradientId = useId();
  const otherDates = dashedDates ?? dates;
  const geo = useMemo(() => {
    if (dates.length < 2) return null;
    const start = dates[0];
    const end = dates[dates.length - 1];
    const domain = yDomain(dashed ? [values, dashed] : [values]);
    const main = timePath(dates, values, start, end, domain, VIEW_W, height);
    const area = timeArea(dates, values, start, end, domain, VIEW_W, height);
    const other = dashed ? timePath(otherDates, dashed, start, end, domain, VIEW_W, height) : '';
    const last = values[values.length - 1];
    const lastY = (1 - (last - domain.lo) / (domain.hi - domain.lo || 1)) * height;
    const between = monthTicks(start, end, 4).filter(
      (d) => timeFraction(d, start, end) > 0.18 && timeFraction(d, start, end) < 0.82
    );
    return { start, end, main, area, other, lastY, ticks: [start, ...between.slice(0, 2), end] };
  }, [dates, values, dashed, otherDates, height]);

  if (!geo) return <div style={{ height: height + (axis ? 22 : 0) }} aria-hidden="true" />;
  const color = tone === 'accent' ? 'rgb(var(--accent))' : 'rgb(var(--fg-2))';
  return (
    <div>
      <div className="relative" style={{ height }}>
        <svg
          role="img"
          aria-label={label}
          viewBox={`0 0 ${VIEW_W} ${height}`}
          preserveAspectRatio="none"
          width="100%"
          height={height}
          className="block overflow-visible"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={tone === 'accent' ? 0.22 : 0.14} />
              <stop offset="100%" stopColor={color} stopOpacity="0.01" />
            </linearGradient>
          </defs>
          {geo.area && <path d={geo.area} fill={`url(#${gradientId})`} />}
          {geo.other && (
            <path
              d={geo.other}
              fill="none"
              stroke="rgb(var(--fg-3))"
              strokeWidth={1}
              strokeDasharray="3 3"
              vectorEffect="non-scaling-stroke"
            />
          )}
          <path
            d={geo.main}
            fill="none"
            stroke={color}
            strokeWidth={tone === 'accent' ? 1.6 : 1.3}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {endDot && (
          <i
            aria-hidden="true"
            className="absolute right-0 h-[7px] w-[7px] -translate-y-1/2 translate-x-1/2 rounded-full bg-accent shadow-[0_0_0_3px_rgb(var(--accent)/0.18)]"
            style={{ top: geo.lastY }}
          />
        )}
      </div>
      {axis && (
        <div className="relative mt-2 h-[14px] font-mono text-[10.5px] text-fg-3">
          {geo.ticks.map((d, i) => {
            const f = timeFraction(d, geo.start, geo.end);
            const shift = i === 0 ? '0%' : i === geo.ticks.length - 1 ? '-100%' : '-50%';
            return (
              <span
                key={d.getTime()}
                className="absolute whitespace-nowrap"
                style={{ left: `${(f * 100).toFixed(2)}%`, transform: `translateX(${shift})` }}
              >
                {tick(d)}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
