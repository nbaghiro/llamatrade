import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { useMemo, useState, type ReactNode } from 'react';

import {
  alignTo,
  figuresFromCurve,
  longDate,
  monthLabel,
  type LogLine,
  type PartialFigures,
  type RebalanceFrequency,
  type RunPhase,
  type TradeInput,
} from '../../lib/backtestView';
import { formatNumber, formatPct } from '../../lib/format';
import { Pct } from '../ui/Num';
import { Segmented } from '../ui/Tabs';

import { LOG_SCALE_FROM_YEARS, scheduleFor, yearsBetween } from './annotations';
import { Cells, KvList, Pending, RunLogList, type Cell } from './parts';
import { RunCurve } from './RunCurve';
import { runMeta, toCurve } from './runData';
import { RunProgressFrame } from './RunProgressFrame';

interface RunPanelProps {
  run: BacktestRun | null;
  phase: RunPhase;
  log: readonly LogLine[];
  partial: PartialFigures;
  progress: number;
  currentDate: string;
  strategyName: string;
  rebalance: RebalanceFrequency | null;
  /** The run's trades for the holding lanes: null while loading, omitted where not fetched. */
  trades?: readonly TradeInput[] | null;
  /** Replaces the result column when a run fails. */
  failure?: ReactNode;
}

/**
 * The results panel, which is also the running state: the log fills beside the run's dates and
 * figures that need the whole run wait as dots, so nothing moves when it completes.
 */
export function RunPanel({
  run,
  phase,
  log,
  partial,
  progress,
  currentDate,
  strategyName,
  rebalance,
  trades,
  failure,
}: RunPanelProps) {
  const [span, setSpan] = useState<'all' | '1y'>('all');
  const meta = runMeta(run);
  const metrics = run?.results?.metrics;
  const done = phase === 'completed' && Boolean(metrics);
  const failed = phase === 'failed' || phase === 'cancelled';
  const pct = done ? 100 : Math.max(0, Math.min(100, progress));
  const bench = meta.benchmark;
  const long =
    meta.start && meta.end ? yearsBetween(meta.start, meta.end) > LOG_SCALE_FROM_YEARS : false;
  const [scaleChoice, setScale] = useState<'linear' | 'log' | null>(null);
  const scale = scaleChoice ?? (long ? 'log' : 'linear');

  const chart = useMemo(() => {
    const eq = toCurve(run?.results?.equityCurve);
    if (eq.values.length < 2) return null;
    const from = span === '1y' ? Math.max(0, eq.values.length - 252) : 0;
    const dates = eq.dates.slice(from);
    const values = eq.values.slice(from);
    const benchRaw = alignTo(dates, toCurve(run?.results?.benchmarkEquityCurve));
    const benchOk = benchRaw.every((v): v is number => v !== null);
    return { dates, values, bench: benchOk ? benchRaw : null };
  }, [run, span]);

  const benchFig = useMemo(
    () => figuresFromCurve(toCurve(run?.results?.benchmarkEquityCurve).values),
    [run]
  );

  const through = currentDate ? new Date(`${currentDate}T00:00:00Z`) : null;
  const startMs = meta.start?.getTime() ?? null;
  const endMs = meta.end?.getTime() ?? null;
  const schedule = useMemo(
    () =>
      scheduleFor(
        startMs === null ? null : new Date(startMs),
        endMs === null ? null : new Date(endMs),
        rebalance
      ),
    [startMs, endMs, rebalance]
  );

  const afterRun = (label: string, render: () => ReactNode, sub?: ReactNode): Cell => ({
    label,
    value: done ? render() : <Pending label="Shown after the run" />,
    sub: done ? sub : 'after the run',
  });

  const vs = (v: number | undefined, fmt: (x: number) => string) =>
    bench && benchFig && v !== undefined ? `${bench} ${fmt(v)}` : undefined;
  const signed = (x: number) => formatPct(x, { dp: 1, signed: true });
  const ratio = (x: number) => formatNumber(x, { dp: 2 });

  const cells: Cell[] = [
    {
      label: 'Total return',
      value: done ? (
        <Pct value={toNumber(metrics?.totalReturn)} pnl dp={1} />
      ) : partial.totalReturn !== null ? (
        <Pct value={partial.totalReturn} pnl dp={1} />
      ) : (
        <Pending />
      ),
      sub: done
        ? bench
          ? `${bench} ${signed(toNumber(metrics?.benchmarkReturn))}`
          : undefined
        : partial.totalReturn !== null && partial.benchmarkReturn !== null && bench
          ? `${bench} ${signed(partial.benchmarkReturn)}`
          : 'so far',
    },
    afterRun(
      'CAGR',
      () => <Pct value={toNumber(metrics?.annualizedReturn)} pnl dp={1} />,
      vs(benchFig?.cagr, signed)
    ),
    afterRun(
      'Sharpe',
      () => formatNumber(toNumber(metrics?.sharpeRatio), { dp: 2 }),
      vs(benchFig?.sharpe, ratio)
    ),
    afterRun(
      'Sortino',
      () => formatNumber(toNumber(metrics?.sortinoRatio), { dp: 2 }),
      vs(benchFig?.sortino, ratio)
    ),
    {
      label: 'Max drawdown',
      value: done ? (
        <Pct value={-Math.abs(toNumber(metrics?.maxDrawdown))} pnl dp={1} />
      ) : partial.maxDrawdown !== null ? (
        <Pct value={partial.maxDrawdown} pnl dp={1} />
      ) : (
        <Pending />
      ),
      sub: done
        ? (vs(benchFig?.maxDrawdown, signed) ??
          `${formatNumber(toNumber(metrics?.maxDrawdownDurationDays), { dp: 0 })} days`)
        : 'so far',
    },
    afterRun(
      'Volatility',
      () => formatPct(toNumber(metrics?.volatility), { dp: 1 }),
      vs(benchFig?.volatility, (x) => formatPct(x, { dp: 1 }))
    ),
  ];

  const passed = through ? schedule.filter((d) => d.getTime() <= through.getTime()).length : 0;
  const status = done
    ? null
    : `${formatNumber(pct, { dp: 0 })}%${currentDate ? ` · through ${currentDate}` : ''}${
        schedule.length ? ` · ${passed} of ${schedule.length} rebalances` : ''
      }`;

  return (
    <section
      aria-label={`${strategyName} run`}
      aria-busy={!done && !failed}
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div
        className="relative h-0.5 bg-line"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i
          className={`block h-full transition-[width] duration-500 motion-reduce:transition-none ${
            failed ? 'bg-risk' : 'bg-accent-fill'
          }`}
          style={{ width: `${failed ? Math.max(4, pct) : pct}%` }}
        />
      </div>
      <div className="grid md:grid-cols-[300px_minmax(0,1fr)]">
        <div className="order-last flex flex-col border-t border-line md:order-none md:border-r md:border-t-0">
          <RunLogList lines={log} />
          {done && (
            <div className="mt-auto border-t border-line px-3.5 py-2">
              <KvList
                rows={[
                  [
                    'Rebalances',
                    schedule.length
                      ? `${schedule.length}, ${rebalance}`
                      : (rebalance ?? 'on schedule'),
                  ],
                  ['Trades', formatNumber(metrics?.totalTrades ?? 0, { dp: 0 })],
                  ['Fills', 'close + slippage'],
                ]}
              />
            </div>
          )}
        </div>
        {failure ?? (
          <div className="min-w-0">
            <Cells cells={cells} />
            <div className="px-3.5 pb-2 pt-2.5">
              <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2.5">
                <div className="flex flex-wrap gap-3.5 text-[11.5px] text-fg-2">
                  <span className="inline-flex items-center gap-1.5">
                    <i aria-hidden="true" className="w-3.5 border-t-[1.5px] border-accent" />
                    {strategyName}
                  </span>
                  {bench && (
                    <span className="inline-flex items-center gap-1.5">
                      <i aria-hidden="true" className="w-3.5 border-t border-dashed border-fg-3" />
                      {bench}
                    </span>
                  )}
                </div>
                {status ? (
                  <span className="num text-[11.5px] text-fg-3">{status}</span>
                ) : (
                  <span className="flex flex-wrap gap-2">
                    {long && (
                      <Segmented
                        label="Scale"
                        value={scale}
                        onChange={setScale}
                        options={[
                          { key: 'linear', label: 'Linear' },
                          { key: 'log', label: 'Log' },
                        ]}
                      />
                    )}
                    <Segmented
                      label="Chart range"
                      value={span}
                      onChange={setSpan}
                      options={[
                        { key: '1y', label: '1Y' },
                        { key: 'all', label: 'All' },
                      ]}
                    />
                  </span>
                )}
              </div>
              {done && chart ? (
                <RunCurve
                  strategyName={strategyName}
                  benchmark={bench}
                  dates={chart.dates}
                  values={chart.values}
                  benchValues={chart.bench}
                  trades={trades}
                  log={scale === 'log'}
                />
              ) : meta.start && meta.end ? (
                <RunProgressFrame
                  start={meta.start}
                  end={meta.end}
                  through={done ? meta.end : through}
                  marker={through ? `Simulated to ${longDate(through)}` : undefined}
                  rebalances={schedule}
                  doneNote={
                    done
                      ? 'This run has no equity points.'
                      : 'The curve appears when the run completes.'
                  }
                  aheadNote={
                    through
                      ? `${monthLabel(currentDate.slice(0, 7))} to ${monthLabel(meta.end.toISOString().slice(0, 7))} hasn't been simulated yet.`
                      : 'The simulation starts once the price history is loaded.'
                  }
                />
              ) : (
                <p className="m-0 py-16 text-center text-[12.5px] text-fg-3">
                  {done
                    ? 'This run has no equity points.'
                    : 'The curve appears when the run completes.'}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
