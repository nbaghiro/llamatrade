import { useMemo } from 'react';

import { areaPath, linePath, yDomain, type Plot } from '../../lib/chart/scale';
import { formatMoney } from '../../lib/format';
import { exampleBacktest } from '../../lib/illustrative';
import { LineChart } from '../charts';
import { useWidth } from '../charts/useWidth';
import { Num, Pct } from '../ui/Num';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = (d: Date) => `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
const thousands = (v: number) => `${Math.round(v / 1000)}k`;

const TITLE = 'Recession Radar, version 3';
const SHORT_FOOTNOTE =
  "Illustrative figures, not anyone's account. Past results don't predict future returns.";
const FOOTNOTE =
  "Illustrative figures, not anyone's account. A backtest replays history with the same engine that runs paper and live sessions, and past results don't predict future returns.";

function Legend({ benchmark }: { benchmark: string }) {
  return (
    <div className="flex items-center gap-3.5 text-[11.5px] text-fg-2">
      <span className="inline-flex items-center gap-1.5">
        <i aria-hidden="true" className="inline-block w-3.5 border-t-2 border-accent" />
        Recession Radar
      </span>
      <span className="inline-flex items-center gap-1.5">
        <i
          aria-hidden="true"
          className="inline-block w-3.5 border-t-[1.5px] border-dashed border-fg-3"
        />
        {benchmark}
      </span>
    </div>
  );
}

function Figure({
  label,
  children,
  bench,
}: {
  label: string;
  children: React.ReactNode;
  bench: React.ReactNode;
}) {
  return (
    <div className="grid gap-0.5 py-2.5 text-[11.5px] [&+&]:border-l [&+&]:border-line [&+&]:pl-3.5">
      <span className="text-[11px] font-medium text-fg-3">{label}</span>
      <div className="text-[22px] leading-tight tracking-[-0.02em]">{children}</div>
      <span className="num text-fg-3">{bench}</span>
    </div>
  );
}

/** The fixed Recession Radar example against SPY, shown beside the sign-in forms. */
export function ExampleBacktestPanel({ compact = false }: { compact?: boolean }) {
  const ex = exampleBacktest();
  const s = ex.strategyStats;
  const b = ex.benchmarkStats;
  const range = `${day(ex.days[0])} to ${day(ex.days[ex.days.length - 1])}`;
  return (
    <section aria-label="Example backtest" className="grid w-full max-w-[640px] gap-[18px]">
      <div>
        <span className="text-[11px] font-medium text-fg-3">Example backtest</span>
        <h2 className="mt-1 text-[20px] font-semibold leading-tight tracking-[-0.015em]">
          {TITLE}
        </h2>
        <div className="mt-[3px] text-[12px] text-fg-3">
          {range} · {formatMoney(ex.startingCapital, { dp: 0 })} · benchmark {ex.benchmark}
        </div>
      </div>
      <div className="grid grid-cols-3 border-y border-line">
        <Figure
          label="Total return"
          bench={
            <>
              {ex.benchmark} <Pct value={b.total} signed dp={1} />
            </>
          }
        >
          <Pct value={s.total} pnl dp={1} />
        </Figure>
        <Figure
          label="Sharpe"
          bench={
            <>
              {ex.benchmark} <Num value={b.sharpe} />
            </>
          }
        >
          <Num value={s.sharpe} />
        </Figure>
        <Figure
          label="Max drawdown"
          bench={
            <>
              {ex.benchmark} <Pct value={b.mdd} dp={1} />
            </>
          }
        >
          <Pct value={s.mdd} dp={1} />
        </Figure>
      </div>
      <div className="grid gap-2">
        <Legend benchmark={ex.benchmark} />
        <LineChart
          label={`Example backtest: Recession Radar against ${ex.benchmark}, illustrative`}
          dates={ex.days}
          series={[
            { values: ex.strategy, kind: 'main', area: true },
            { values: ex.benchmarkValues, kind: 'bench' },
          ]}
          height={compact ? 200 : 270}
          yFormat={thousands}
        />
      </div>
      <p className="m-0 max-w-[520px] text-[11.5px] text-fg-3">
        {compact ? SHORT_FOOTNOTE : FOOTNOTE}
      </p>
    </section>
  );
}

function MiniPair({ main, bench }: { main: readonly number[]; bench: readonly number[] }) {
  const [ref, width] = useWidth<HTMLDivElement>(320);
  const height = 72;
  const plot: Plot = useMemo(
    () => ({
      width,
      height,
      pad: { t: 4, r: 0, b: 4, l: 0 },
      domain: yDomain([main, bench]),
      count: main.length,
    }),
    [width, main, bench]
  );
  return (
    <div ref={ref} className="w-full">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden="true"
        className="block"
      >
        <path d={areaPath(plot, main, plot.domain.lo)} fill="rgb(var(--accent))" opacity={0.09} />
        <path
          d={linePath(plot, bench)}
          fill="none"
          stroke="rgb(var(--fg-3))"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <path
          d={linePath(plot, main)}
          fill="none"
          stroke="rgb(var(--accent))"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

/** The same example as a strip above the form on narrow screens. */
export function ExampleBacktestStrip() {
  const ex = exampleBacktest();
  return (
    <section
      aria-label="Example backtest"
      className="grid gap-1.5 rounded-panel border border-line bg-panel px-3.5 pb-2 pt-3"
    >
      <div className="flex items-center justify-between gap-2.5">
        <span className="text-[11px] font-medium text-fg-3">
          Example backtest · Recession Radar v3
        </span>
        <Pct value={ex.strategyStats.total} pnl dp={1} className="text-[13px]" />
      </div>
      <MiniPair main={ex.strategy} bench={ex.benchmarkValues} />
      <div className="text-[11.5px] text-fg-3">
        {ex.benchmark} <Pct value={ex.benchmarkStats.total} signed dp={1} /> over the same two
        years. Illustrative.
      </div>
    </section>
  );
}
