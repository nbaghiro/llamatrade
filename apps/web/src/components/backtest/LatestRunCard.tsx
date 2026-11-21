import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { alignTo, figuresFromCurve } from '../../lib/backtestView';
import { formatNumber, formatPct } from '../../lib/format';
import { AnnotatedCurve } from '../charts';
import { Pct } from '../ui/Num';
import { StatList } from '../ui/StatList';

import { runMeta, toCurve } from './runData';
import { runWhen } from './runLabels';
import { openSessionLabel, type StrategySession } from './strategySessions';

/** The newest finished run with its curve and figures, above the list (backtests/phone A). */
export function LatestRunCard({
  run,
  strategyName,
  session = null,
}: {
  run: BacktestRun;
  strategyName: string;
  /** The session running this run's version, when one does. */
  session?: StrategySession | null;
}) {
  const meta = runMeta(run);
  const m = run.results?.metrics;
  const curve = useMemo(() => {
    const eq = toCurve(run.results?.equityCurve);
    const benchCurve = toCurve(run.results?.benchmarkEquityCurve);
    const aligned = alignTo(eq.dates, benchCurve);
    const bench = aligned.every((v): v is number => v !== null) ? aligned : undefined;
    return { ...eq, bench, benchFig: figuresFromCurve(benchCurve.values) };
  }, [run]);
  if (!m) return null;
  const total = toNumber(m.totalReturn);
  const bench = meta.benchmark;
  const gap = bench ? (total - toNumber(m.benchmarkReturn)) * 100 : null;
  const vs = (v: number | undefined, dp = 1, pct = true) =>
    bench && v !== undefined
      ? ` · ${bench} ${pct ? formatPct(v, { dp }) : formatNumber(v, { dp })}`
      : '';

  return (
    <section className="panel-rim min-w-0 overflow-hidden px-4 pb-3 pt-3.5">
      <div className="flex items-baseline justify-between gap-3 text-[11px] font-medium text-fg-3">
        <span>Latest result · finished {runWhen(run)}</span>
        <span>Backtest</span>
      </div>
      <div className="mt-1 text-[13px] font-semibold">
        {strategyName} v{run.strategyVersion}
      </div>
      <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2.5">
        <span className="font-mono text-[28px] font-medium tracking-[-0.02em]">
          <Pct value={total} pnl dp={1} />
        </span>
        {bench && m.benchmarkReturn && (
          <span className="num text-[12px] text-fg-2">
            {bench} {formatPct(toNumber(m.benchmarkReturn), { dp: 1, signed: true })}
          </span>
        )}
      </div>
      {gap !== null && (
        <p className="m-0 mt-0.5 text-[12px] text-fg-2">
          {formatNumber(Math.abs(gap), { dp: 1 })} points {gap >= 0 ? 'more' : 'less'} than {bench}{' '}
          over the same dates.
        </p>
      )}
      {curve.values.length > 1 && (
        <div className="mt-2">
          <AnnotatedCurve
            label={`${strategyName} equity${curve.bench ? ` against ${bench}` : ''}`}
            dates={curve.dates}
            values={curve.values}
            benchmark={curve.bench}
            height={130}
          />
        </div>
      )}
      <StatList
        className="mt-1"
        items={[
          {
            label: 'CAGR',
            value: `${formatPct(toNumber(m.annualizedReturn), { dp: 1 })}${vs(curve.benchFig?.cagr)}`,
          },
          {
            label: 'Sharpe',
            value: `${formatNumber(toNumber(m.sharpeRatio), { dp: 2 })}${vs(curve.benchFig?.sharpe, 2, false)}`,
          },
          {
            label: 'Max drawdown',
            value: `${formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1 })}${vs(curve.benchFig?.maxDrawdown)}`,
          },
          { label: 'Trades', value: formatNumber(m.totalTrades, { dp: 0 }) },
        ]}
      />
      {session?.href && (
        <Link to={session.href} className="btn btn-primary mt-2.5 w-full justify-center">
          {openSessionLabel(session)}
        </Link>
      )}
      <Link to={`/backtest/${run.id}`} className="btn btn-secondary mt-2 w-full justify-center">
        Open result
      </Link>
    </section>
  );
}
