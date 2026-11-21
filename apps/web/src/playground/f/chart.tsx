import { useId, useState, type MouseEvent } from 'react';

import { useWidth } from '../../components/charts/useWidth';

import { dayLabel, drawdown, fullDay, monthLabel, pts, type Window } from './model';

const PR = 52;
const PB = 20;

function niceStep(span: number, target: number) {
  const raw = span / target;
  return [0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100].find((s) => s >= raw) ?? 200;
}

const pathOf = (s: readonly number[], x: (i: number) => number, y: (v: number) => number) =>
  s.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');

/**
 * A line against SPY in percent from the start of the window, drawn tight: the ink line over a
 * dashed SPY, numbered markers, a hover readout and an optional drop-from-high strip.
 */
export function PerfChart({
  w,
  height = 200,
  mainLabel = 'Account',
  benchLabel = 'SPY',
  ddHeight = 0,
  worst,
}: {
  w: Window;
  height?: number;
  mainLabel?: string;
  benchLabel?: string;
  /** Height of the drop-from-high strip; 0 hides it. */
  ddHeight?: number;
  worst?: number;
}) {
  const gid = useId().replace(/:/g, '');
  const [ref, W] = useWidth<HTMLDivElement>(700);
  const [hov, setHov] = useState<number | null>(null);
  const { main, bench, dates } = w;
  const n = main.length;
  const PT = w.markers.length ? 24 : 10;
  let lo = Math.min(...main, ...bench, 0);
  let hi = Math.max(...main, ...bench, 0);
  const st = niceStep(hi - lo || 1, height < 180 ? 3 : 4);
  lo = Math.floor(lo / st) * st;
  hi = Math.ceil(hi / st) * st;
  const plotW = Math.max(120, W - PR);
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * plotW : 0);
  const y = (v: number) => PT + (1 - (v - lo) / (hi - lo || 1)) * (height - PT - PB);
  const grid: number[] = [];
  for (let v = lo; v <= hi + 1e-9; v += st) grid.push(v);
  const span = dates[n - 1].getTime() - dates[0].getTime();
  const fmt = span > 200 * 86_400_000 ? monthLabel : dayLabel;
  const nt = W < 520 ? 3 : 5;
  const ticks = [
    ...new Set(Array.from({ length: nt }, (_, k) => Math.round((k * (n - 1)) / (nt - 1)))),
  ];
  const ea = main[n - 1];
  const eb = bench[n - 1];
  let ya = y(ea);
  let yb = y(eb);
  if (Math.abs(ya - yb) < 13) {
    const d = ya < yb ? -6.5 : 6.5;
    ya += d;
    yb -= d;
  }

  const raw = drawdown(main);
  const k = worst !== undefined && Math.min(...raw) < 0 ? worst / Math.min(...raw) : 1;
  const dd = raw.map((v) => v * k);
  const ddb = drawdown(bench);
  const dlo = Math.min(-1, ...dd, ...ddb);
  const dy = (v: number) => 4 + (v / dlo) * (ddHeight - 8);
  const worstAt = dd.indexOf(Math.min(...dd));

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left) / plotW) * (n - 1));
    setHov(i >= 0 && i < n ? i : null);
  };

  return (
    <div ref={ref} className="relative w-full select-none">
      <svg
        width={W}
        height={height}
        viewBox={`0 0 ${W} ${height}`}
        role="img"
        aria-label={`${mainLabel} against ${benchLabel}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHov(null)}
        className="block overflow-visible"
      >
        <defs>
          <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="rgb(var(--fg))" stopOpacity="0.12" />
            <stop offset="1" stopColor="rgb(var(--fg))" stopOpacity="0" />
          </linearGradient>
        </defs>
        {grid.map((v) => (
          <g key={v}>
            <line
              x1={0}
              x2={plotW}
              y1={y(v)}
              y2={y(v)}
              stroke="rgb(var(--fg))"
              strokeOpacity={v === 0 ? 0.26 : 0.1}
              strokeDasharray={v === 0 ? undefined : '1 4'}
            />
            {Math.abs(y(v) - ya) > 11 && Math.abs(y(v) - yb) > 11 && (
              <text
                x={W - 2}
                y={y(v) + 3.5}
                textAnchor="end"
                className="fill-fg-3 font-mono text-[10px]"
              >
                {v === 0 ? '0%' : pts(v).replace('.0', '')}
              </text>
            )}
          </g>
        ))}
        {w.markers.map((m) => (
          <g key={m.n}>
            <line
              x1={x(m.i)}
              x2={x(m.i)}
              y1={16}
              y2={height - PB}
              stroke="rgb(var(--fg))"
              strokeOpacity={0.16}
              strokeDasharray="1 3"
            />
            <rect
              x={x(m.i) - 6.5}
              y={2}
              width={13}
              height={13}
              rx={2.5}
              fill="rgb(var(--canvas))"
              stroke="rgb(var(--line-strong))"
            />
            <text x={x(m.i)} y={11.5} textAnchor="middle" className="fill-fg font-mono text-[9px]">
              {m.n}
            </text>
          </g>
        ))}
        <path
          d={`${pathOf(main, x, y)} L${x(n - 1)},${height - PB} L0,${height - PB} Z`}
          fill={`url(#${gid})`}
        />
        <path
          d={pathOf(bench, x, y)}
          fill="none"
          stroke="rgb(var(--fg-3))"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <path
          d={pathOf(main, x, y)}
          fill="none"
          stroke="rgb(var(--fg))"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
        <circle cx={x(n - 1)} cy={y(ea)} r={2.5} fill="rgb(var(--fg))" />
        <text x={plotW + 6} y={ya + 3.5} className="fill-fg font-mono text-[10.5px] font-medium">
          {pts(ea)}
        </text>
        <text x={plotW + 6} y={yb + 3.5} className="fill-fg-3 font-mono text-[10.5px]">
          {pts(eb)}
        </text>
        {ticks.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={height - 5}
            textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
            className="fill-fg-3 font-mono text-[10px]"
          >
            {fmt(dates[i])}
          </text>
        ))}
        {hov !== null && (
          <g>
            <line
              x1={x(hov)}
              x2={x(hov)}
              y1={PT - 6}
              y2={height - PB}
              stroke="rgb(var(--fg))"
              strokeOpacity={0.4}
            />
            <circle cx={x(hov)} cy={y(bench[hov])} r={2.2} fill="rgb(var(--fg-3))" />
            <circle
              cx={x(hov)}
              cy={y(main[hov])}
              r={3}
              fill="rgb(var(--canvas))"
              stroke="rgb(var(--fg))"
              strokeWidth={1.5}
            />
          </g>
        )}
      </svg>
      {hov !== null && (
        <div
          className="pointer-events-none absolute top-2 z-10 grid min-w-[150px] gap-0.5 rounded-[6px] border border-line-strong bg-canvas px-2.5 py-1.5 font-mono text-[11px] tabular-nums shadow-lg"
          style={{ left: Math.min(Math.max(0, x(hov) + 10), plotW - 156) }}
        >
          <span className="text-fg-3">{fullDay(dates[hov])}</span>
          <span className="flex justify-between gap-4">
            <span className="text-fg-2">{mainLabel}</span>
            <b className="font-medium text-fg">{pts(main[hov])}</b>
          </span>
          <span className="flex justify-between gap-4">
            <span className="text-fg-2">{benchLabel}</span>
            <span className="text-fg-3">{pts(bench[hov])}</span>
          </span>
        </div>
      )}
      {ddHeight > 0 && (
        <div className="mt-2 border-t border-line pt-1.5">
          <div className="mb-1 flex items-center justify-between font-mono text-[10.5px] text-fg-3">
            <span className="uppercase tracking-[0.08em]">Drop from high</span>
            <span className="tabular-nums">
              worst {pts(dd[worstAt])} · {dayLabel(dates[worstAt])}
            </span>
          </div>
          <svg width={W} height={ddHeight} viewBox={`0 0 ${W} ${ddHeight}`} aria-hidden="true">
            <line x1={0} x2={plotW} y1={4} y2={4} stroke="rgb(var(--line-strong))" />
            <path
              d={`M0,4 ${dd.map((v, i) => `L${x(i).toFixed(1)},${dy(v).toFixed(1)}`).join('')} L${plotW},4 Z`}
              fill="rgb(var(--loss))"
              opacity={0.16}
            />
            <path d={pathOf(dd, x, dy)} fill="none" stroke="rgb(var(--loss))" strokeWidth={1} />
            <path
              d={pathOf(ddb, x, dy)}
              fill="none"
              stroke="rgb(var(--fg-3))"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text
              x={W - 2}
              y={ddHeight - 4}
              textAnchor="end"
              className="fill-fg-3 font-mono text-[10px]"
            >
              {pts(dlo).replace('.0', '')}
            </text>
            {hov !== null && (
              <line
                x1={x(hov)}
                x2={x(hov)}
                y1={0}
                y2={ddHeight}
                stroke="rgb(var(--fg))"
                strokeOpacity={0.4}
              />
            )}
          </svg>
        </div>
      )}
    </div>
  );
}

export function Legend({
  main = 'Account',
  bench = 'SPY',
  markers,
}: {
  main?: string;
  bench?: string;
  markers?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-3 font-mono text-[10.5px] text-fg-3">
      <span className="inline-flex items-center gap-1.5">
        <i aria-hidden="true" className="w-3 border-t-[1.5px] border-fg" />
        {main}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <i aria-hidden="true" className="w-3 border-t border-dashed border-fg-3" />
        {bench}
      </span>
      {markers && (
        <span className="hidden items-center gap-1.5 lg:inline-flex">
          <i className="grid h-3 w-3 place-items-center rounded-[2px] border border-line-strong text-[8px] not-italic text-fg">
            1
          </i>
          session
        </span>
      )}
    </span>
  );
}
