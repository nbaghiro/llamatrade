import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { useMemo, useState, type ReactNode } from 'react';

import {
  alignTo,
  drawdownOf,
  scheduledRebalances,
  type LogLine,
  type PartialFigures,
  type RebalanceFrequency,
  type RunPhase,
} from '../../lib/backtestView';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { DrawdownBand, LineChart } from '../charts';
import { Pct } from '../ui/Num';
import { SkeletonChart } from '../ui/Skeleton';
import { Segmented } from '../ui/Tabs';

import { Cells, KvList, Pending, RunLogList, type Cell } from './parts';
import { runMeta, toCurve } from './runData';

const EQ_HEIGHT = 262;
const DD_HEIGHT = 76;

interface RunPanelProps {
  run: BacktestRun | null;
  phase: RunPhase;
  log: readonly LogLine[];
  partial: PartialFigures;
  progress: number;
  currentDate: string;
  strategyName: string;
  rebalance: RebalanceFrequency | null;
  /** Replaces the result column when a run fails. */
  failure?: ReactNode;
}

const yMoney = (v: number) =>
  Math.abs(v) >= 10_000 ? `$${formatNumber(v / 1000, { dp: 0 })}k` : formatMoney(v, { dp: 0 });

/**
 * The results panel, which is also the running state: the log fills beside the curve and
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
  failure,
}: RunPanelProps) {
  const [span, setSpan] = useState<'all' | '1y'>('all');
  const meta = runMeta(run);
  const metrics = run?.results?.metrics;
  const done = phase === 'completed' && Boolean(metrics);
  const failed = phase === 'failed' || phase === 'cancelled';
  const pct = done ? 100 : Math.max(0, Math.min(100, progress));
  const bench = meta.benchmark;

  const chart = useMemo(() => {
    const eq = toCurve(run?.results?.equityCurve);
    if (eq.values.length < 2) return null;
    const from = span === '1y' ? Math.max(0, eq.values.length - 252) : 0;
    const dates = eq.dates.slice(from);
    const values = eq.values.slice(from);
    const benchRaw = alignTo(dates, toCurve(run?.results?.benchmarkEquityCurve));
    const benchOk = benchRaw.every((v): v is number => v !== null);
    return { dates, values, bench: benchOk ? benchRaw : null, drawdown: drawdownOf(values) };
  }, [run, span]);

  const schedule =
    meta.start && meta.end
      ? scheduledRebalances(
          meta.start,
          meta.end,
          rebalance,
          done ? meta.end : currentDate ? new Date(`${currentDate}T00:00:00Z`) : null
        )
      : null;

  const afterRun = (label: string, render: () => ReactNode, sub?: ReactNode): Cell => ({
    label,
    value: done ? render() : <Pending label="Shown after the run" />,
    sub: done ? sub : 'after the run',
  });

  const benchSub = (v: number | null) =>
    bench && v !== null ? `${bench} ${formatPct(v, { dp: 1, signed: true })}` : undefined;

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
        ? benchSub(bench ? toNumber(metrics?.benchmarkReturn) : null)
        : partial.totalReturn !== null
          ? (benchSub(partial.benchmarkReturn) ?? 'so far')
          : 'so far',
    },
    afterRun('CAGR', () => <Pct value={toNumber(metrics?.annualizedReturn)} pnl dp={1} />),
    afterRun('Sharpe', () => formatNumber(toNumber(metrics?.sharpeRatio), { dp: 2 })),
    afterRun('Sortino', () => formatNumber(toNumber(metrics?.sortinoRatio), { dp: 2 })),
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
        ? `${formatNumber(toNumber(metrics?.maxDrawdownDurationDays), { dp: 0 })} days`
        : 'so far',
    },
    afterRun('Volatility', () => formatPct(toNumber(metrics?.volatility), { dp: 1 })),
  ];

  const status = done
    ? null
    : `${formatNumber(pct, { dp: 0 })}%${currentDate ? ` · through ${currentDate}` : ''}${
        schedule ? ` · ${schedule.done} of ${schedule.total} rebalances` : ''
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
                    schedule ? `${schedule.total}, ${rebalance}` : (rebalance ?? 'on schedule'),
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
                  <Segmented
                    label="Chart range"
                    value={span}
                    onChange={setSpan}
                    options={[
                      { key: '1y', label: '1Y' },
                      { key: 'all', label: 'All' },
                    ]}
                  />
                )}
              </div>
              {!done && schedule && schedule.total <= 60 && (
                <div
                  className="mb-2 grid gap-[3px]"
                  style={{ gridTemplateColumns: `repeat(${schedule.total}, minmax(0, 1fr))` }}
                  aria-label={`${schedule.done} of ${schedule.total} scheduled rebalances`}
                  role="img"
                >
                  {Array.from({ length: schedule.total }, (_, k) => (
                    <i
                      key={k}
                      className={`h-2 rounded-[1px] ${
                        k < schedule.done
                          ? !done && k === schedule.done - 1
                            ? 'bg-accent-fill'
                            : 'bg-chart-3'
                          : 'bg-sunk ring-1 ring-inset ring-line'
                      }`}
                    />
                  ))}
                </div>
              )}
              {done && chart ? (
                <LineChart
                  label={`${strategyName} equity${chart.bench ? ` against ${bench}` : ''}`}
                  dates={chart.dates}
                  height={EQ_HEIGHT}
                  yFormat={yMoney}
                  series={[
                    { values: chart.values, kind: 'main', area: true, label: strategyName },
                    ...(chart.bench
                      ? [{ values: chart.bench, kind: 'bench' as const, label: bench }]
                      : []),
                  ]}
                  tooltip={(i) => (
                    <>
                      <b className="block font-medium text-fg-3">
                        {chart.dates[i]?.toISOString().slice(0, 10)}
                      </b>
                      {strategyName} {formatMoney(chart.values[i])}
                      {chart.bench && (
                        <span className="block text-fg-2">
                          {bench} {formatMoney(chart.bench[i])}
                        </span>
                      )}
                    </>
                  )}
                />
              ) : (
                <div className="relative">
                  <SkeletonChart height={EQ_HEIGHT} />
                  <p className="absolute inset-0 m-0 grid place-items-center text-center text-[12.5px] text-fg-3">
                    {done
                      ? 'This run has no equity points.'
                      : 'The curve draws when the run completes.'}
                  </p>
                </div>
              )}
              <div className="mt-1.5 text-[11px] font-medium text-fg-3">Drawdown from peak</div>
              {done && chart ? (
                <DrawdownBand dates={chart.dates} drawdown={chart.drawdown} height={DD_HEIGHT} />
              ) : (
                <SkeletonChart height={DD_HEIGHT} />
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
