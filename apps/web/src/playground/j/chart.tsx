import { useId, useState, type MouseEvent } from 'react';

import { useWidth } from '../../components/charts/useWidth';

import { dayLabel, drawdown, fullDay, monthLabel, pts, type Window } from './model';

const PR = 64;
const PT = 30;
const PB = 24;

function niceStep(span: number, target: number) {
  const raw = span / target;
  return [0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50].find((s) => s >= raw) ?? 100;
}

const pathOf = (s: readonly number[], x: (i: number) => number, y: (v: number) => number) =>
  s.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');

/**
 * A line against SPY in percent from the start of the window: the white line over a dashed SPY,
 * a soft fill, numbered markers, a hover readout and an optional drawdown strip.
 */
export function PerfChart({
  w,
  height = 300,
  mainLabel = 'Account',
  benchLabel = 'SPY',
  drawdownStrip = true,
  worst,
}: {
  w: Window;
  height?: number;
  mainLabel?: string;
  benchLabel?: string;
  drawdownStrip?: boolean;
  /** Scales the drawdown strip so its low meets a known figure, e.g. a backtest's max drawdown. */
  worst?: number;
}) {
  const [ref, W] = useWidth<HTMLDivElement>(900);
  const [hov, setHov] = useState<number | null>(null);
  const fid = `g-fill-${useId().replace(/:/g, '')}`;
  const { main, bench, dates } = w;
  const n = main.length;
  let lo = Math.min(...main, ...bench, 0);
  let hi = Math.max(...main, ...bench, 0);
  const st = niceStep(hi - lo || 1, 4);
  lo = Math.floor(lo / st) * st;
  hi = Math.ceil(hi / st) * st;
  const plotW = Math.max(120, W - PR);
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * plotW : 0);
  const y = (v: number) => PT + (1 - (v - lo) / (hi - lo || 1)) * (height - PT - PB);
  const grid: number[] = [];
  for (let v = lo; v <= hi + 1e-9; v += st) grid.push(v);
  const span = dates[n - 1].getTime() - dates[0].getTime();
  const fmt = span > 200 * 86_400_000 ? monthLabel : dayLabel;
  const ticks = [
    ...new Set(
      Array.from({ length: W < 560 ? 3 : 5 }, (_, k) =>
        Math.round((k * (n - 1)) / (W < 560 ? 2 : 4))
      )
    ),
  ];
  const ea = main[n - 1];
  const eb = bench[n - 1];
  let ya = y(ea);
  let yb = y(eb);
  if (Math.abs(ya - yb) < 16) {
    const d = ya < yb ? -8 : 8;
    ya += d;
    yb -= d;
  }

  const raw = drawdown(main);
  const k = worst !== undefined && Math.min(...raw) < 0 ? worst / Math.min(...raw) : 1;
  const dd = raw.map((v) => v * k);
  const ddb = drawdown(bench);
  const DH = 72;
  const dlo = Math.min(-1, ...dd, ...ddb);
  const dy = (v: number) => 6 + (v / dlo) * (DH - 18);
  const worstAt = dd.indexOf(Math.min(...dd));

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left) / plotW) * (n - 1));
    setHov(i >= 0 && i < n ? i : null);
  };

  return (
    <div ref={ref} className="relative w-full select-none">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-fg-2">
        <span className="inline-flex items-center gap-1.5">
          <i aria-hidden="true" className="w-3.5 border-t-2 border-fg" />
          {mainLabel}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i aria-hidden="true" className="w-3.5 border-t-[1.5px] border-dashed border-fg-3" />
          {benchLabel}
        </span>
        {w.markers.length > 0 && (
          <span className="inline-flex items-center gap-1.5">
            <i className="grid h-3.5 w-3.5 place-items-center rounded-[3px] border border-line-strong font-mono text-[9px] not-italic text-fg">
              1
            </i>
            Session started or stopped
          </span>
        )}
      </div>
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
          <linearGradient id={fid} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="rgb(var(--fg))" stopOpacity="0.14" />
            <stop offset="1" stopColor="rgb(var(--fg))" stopOpacity="0.02" />
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
              strokeOpacity={v === 0 ? 0.28 : 0.12}
              strokeDasharray={v === 0 ? undefined : '1 4'}
            />
            {Math.abs(y(v) - ya) > 13 && Math.abs(y(v) - yb) > 13 && (
              <text
                x={W - 4}
                y={y(v) + 3.5}
                textAnchor="end"
                className="fill-fg-3 font-mono text-[10.5px]"
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
              y1={18}
              y2={height - PB}
              stroke="rgb(var(--fg))"
              strokeOpacity={0.18}
              strokeDasharray="1 3"
            />
            <rect
              x={x(m.i) - 7}
              y={2}
              width={14}
              height={14}
              rx={3}
              fill="rgb(var(--canvas))"
              stroke="rgb(var(--line-strong))"
            />
            <text
              x={x(m.i)}
              y={12.5}
              textAnchor="middle"
              className="fill-fg font-mono text-[9.5px]"
            >
              {m.n}
            </text>
          </g>
        ))}
        <path
          d={`${pathOf(main, x, y)} L${x(n - 1)},${height - PB} L0,${height - PB} Z`}
          fill={`url(#${fid})`}
        />
        <path
          d={pathOf(bench, x, y)}
          fill="none"
          stroke="rgb(var(--fg-3))"
          strokeWidth={1.1}
          strokeDasharray="3 3"
        />
        <path
          d={pathOf(main, x, y)}
          fill="none"
          stroke="rgb(var(--fg))"
          strokeWidth={1.6}
          strokeLinejoin="round"
        />
        <circle cx={x(n - 1)} cy={y(ea)} r={3} fill="rgb(var(--fg))" />
        <text x={plotW + 8} y={ya + 4} className="fill-fg font-mono text-[11px] font-medium">
          {pts(ea)}
        </text>
        <text x={plotW + 8} y={yb + 4} className="fill-fg-3 font-mono text-[11px]">
          {pts(eb)}
        </text>
        {ticks.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={height - 6}
            textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
            className="fill-fg-3 font-mono text-[10.5px]"
          >
            {fmt(dates[i])}
          </text>
        ))}
        {hov !== null && (
          <g>
            <line
              x1={x(hov)}
              x2={x(hov)}
              y1={PT - 8}
              y2={height - PB}
              stroke="rgb(var(--fg))"
              strokeOpacity={0.45}
            />
            <circle cx={x(hov)} cy={y(bench[hov])} r={2.5} fill="rgb(var(--fg-3))" />
            <circle
              cx={x(hov)}
              cy={y(main[hov])}
              r={3.5}
              fill="rgb(var(--canvas))"
              stroke="rgb(var(--fg))"
              strokeWidth={1.5}
            />
          </g>
        )}
      </svg>
      {hov !== null && (
        <div
          className="pointer-events-none absolute top-8 z-10 grid min-w-[150px] gap-1 rounded-[8px] border border-line-strong bg-canvas px-3 py-2 text-[12px] shadow-lg"
          style={{
            left: Math.min(Math.max(0, x(hov) + 12), plotW - 160),
          }}
        >
          <span className="font-mono text-[11px] text-fg-3">{fullDay(dates[hov])}</span>
          <span className="flex justify-between gap-4">
            <span className="text-fg-2">{mainLabel}</span>
            <b className="font-mono font-medium tabular-nums text-fg">{pts(main[hov])}</b>
          </span>
          <span className="flex justify-between gap-4">
            <span className="text-fg-2">{benchLabel}</span>
            <span className="font-mono tabular-nums text-fg-3">{pts(bench[hov])}</span>
          </span>
        </div>
      )}
      {drawdownStrip && (
        <div className="mt-3 border-t border-line pt-2">
          <div className="mb-1 flex items-center justify-between text-[11.5px] text-fg-3">
            <span>Drop from high</span>
            <span className="font-mono tabular-nums">
              Worst {pts(dd[worstAt])} on {dayLabel(dates[worstAt])}
            </span>
          </div>
          <svg
            width={W}
            height={DH}
            viewBox={`0 0 ${W} ${DH}`}
            aria-hidden="true"
            className="block"
          >
            <line x1={0} x2={plotW} y1={6} y2={6} stroke="rgb(var(--line-strong))" />
            <path
              d={`M0,6 ${dd.map((v, i) => `L${x(i).toFixed(1)},${dy(v).toFixed(1)}`).join('')} L${plotW},6 Z`}
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
            <text x={W - 4} y={9.5} textAnchor="end" className="fill-fg-3 font-mono text-[10.5px]">
              0%
            </text>
            <text
              x={W - 4}
              y={DH - 8}
              textAnchor="end"
              className="fill-fg-3 font-mono text-[10.5px]"
            >
              {pts(dlo).replace('.0', '')}
            </text>
            {hov !== null && (
              <line
                x1={x(hov)}
                x2={x(hov)}
                y1={0}
                y2={DH}
                stroke="rgb(var(--fg))"
                strokeOpacity={0.45}
              />
            )}
          </svg>
        </div>
      )}
    </div>
  );
}
