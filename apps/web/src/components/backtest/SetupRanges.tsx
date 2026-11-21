import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { BacktestMetrics } from '@llamatrade/core/proto/backtest_pb';
import type { BacktestConfig } from '@llamatrade/core/stores/backtest';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { curatedRanges, DATA_FLOOR, type CuratedRange } from '../../lib/backtestRanges';
import { longDate, scheduledRebalances, type RebalanceFrequency } from '../../lib/backtestView';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { Pct } from '../ui/Num';

import { durationLabel, estimateSeconds, testedOn } from './rangeSetup';
import { runWhen } from './runLabels';

const DAY_MS = 86_400_000;
const day = (iso: string) => new Date(`${iso}T00:00:00Z`);

interface SetupRangesProps {
  strategyName: string | null;
  strategyId: string;
  /** "v4" and when it was saved, when known. */
  versionLine?: string;
  config: BacktestConfig;
  onChange: (config: Partial<BacktestConfig>) => void;
  rebalance: RebalanceFrequency | null;
  runs: readonly BacktestRun[];
  metrics: Readonly<Record<string, BacktestMetrics>>;
  today?: Date;
}

/**
 * Setup as a question: four curated ranges to pick from, the costs the run uses, how long it
 * should take, and where the strategy has already been tested.
 */
export function SetupRanges({
  strategyName,
  strategyId,
  versionLine,
  config,
  onChange,
  rebalance,
  runs,
  metrics,
  today,
}: SetupRangesProps) {
  const now = useMemo(() => today ?? new Date(), [today]);
  const ranges = useMemo(() => curatedRanges(now), [now]);
  const tested = useMemo(
    () => (strategyId ? testedOn(runs, strategyId, ranges) : []),
    [runs, strategyId, ranges]
  );
  const span =
    config.startDate && config.endDate
      ? (day(config.endDate).getTime() - day(config.startDate).getTime()) / DAY_MS
      : 0;
  const estimate = estimateSeconds(runs, span);
  const picked = (r: CuratedRange) => config.startDate === r.start && config.endDate === r.end;
  const costs = `${formatMoney(config.commission)} per fill + ${formatNumber(config.slippage * 100, { dp: 2 })}%`;

  return (
    <div className="grid gap-3.5">
      <header>
        <h2 className="m-0 text-[22px] font-semibold tracking-[-0.02em]">
          {strategyName ? `What should ${strategyName} be tested on?` : 'Choose a strategy to test'}
        </h2>
        <p className="m-0 mt-1 text-[12.5px] text-fg-3">
          {versionLine ? `${versionLine} · ` : ''}each range below has daily bars from{' '}
          {longDate(day(DATA_FLOOR))} on
        </p>
      </header>

      <div
        role="radiogroup"
        aria-label="Range"
        className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4"
      >
        {ranges.map((r) => {
          const count = scheduledRebalances(day(r.start), day(r.end), rebalance);
          const on = picked(r);
          return (
            <button
              key={r.id}
              type="button"
              role="radio"
              aria-checked={on}
              disabled={!strategyId}
              onClick={() => onChange({ startDate: r.start, endDate: r.end })}
              className={`grid gap-1.5 rounded-panel border bg-panel px-3.5 py-3 text-left transition-colors disabled:opacity-60 ${
                on ? 'border-accent ring-1 ring-accent' : 'border-line hover:border-line-strong'
              }`}
            >
              <span className="flex items-center gap-2 text-[13px] font-semibold">
                <i
                  aria-hidden="true"
                  className={`h-3.5 w-3.5 flex-none rounded-full border ${
                    on ? 'border-[4px] border-accent' : 'border-line-strong'
                  }`}
                />
                {r.label}
              </span>
              <span className="font-mono text-[12px] tabular-nums text-fg">
                {longDate(day(r.start))} → {longDate(day(r.end))}
              </span>
              <span className="text-[11.5px] text-fg-3">
                {count ? `${formatNumber(count.total, { dp: 0 })} rebalances · ` : ''}
                {r.reason}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 rounded-panel border border-line bg-panel px-3.5 py-2.5 text-[12.5px] text-fg-2">
        <span>
          Capital{' '}
          <b className="num font-medium text-fg">{formatMoney(config.initialCapital, { dp: 0 })}</b>
          {' · '}Benchmark <b className="font-medium text-fg">{config.benchmarkSymbol || 'none'}</b>
          {' · '}Costs <b className="num font-medium text-fg">{costs}</b>
          {' · '}Bars <b className="font-medium text-fg">daily, fills at the close</b>
        </span>
        <span className="text-fg-3">
          {estimate !== null ? durationLabel(estimate) : 'No timed runs yet to estimate from'}
        </span>
      </div>

      {strategyName && (
        <section className="overflow-hidden rounded-panel border border-line bg-panel">
          <header className="flex items-center justify-between gap-2 border-b border-line px-3.5 py-2.5">
            <h3 className="m-0 font-sans text-[13px] font-semibold tracking-normal">
              Where {strategyName} has been tested
            </h3>
            <span className="text-[11.5px] text-fg-3">
              Backtests · latest version on each range
            </span>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-[12.5px]">
              <thead>
                <tr className="text-[10.5px] uppercase tracking-[0.04em] text-fg-3">
                  <th className="px-3.5 py-2 text-left font-medium">Range</th>
                  <th className="px-3.5 py-2 text-left font-medium">Last run</th>
                  <th className="px-3.5 py-2 text-right font-medium">Return</th>
                  <th className="px-3.5 py-2 text-right font-medium">
                    {config.benchmarkSymbol || 'Benchmark'}
                  </th>
                  <th className="px-3.5 py-2 text-right font-medium">Max drawdown</th>
                </tr>
              </thead>
              <tbody>
                {tested.map(({ range, run }) => {
                  const m = run ? metrics[run.id] : undefined;
                  return (
                    <tr key={range.id} className="border-t border-line">
                      <td className="px-3.5 py-2">{range.label}</td>
                      <td className="px-3.5 py-2 text-fg-2">
                        {run ? (
                          <Link to={`/backtest/${run.id}`} className="hover:underline">
                            v{run.strategyVersion} · {runWhen(run)}
                          </Link>
                        ) : (
                          <span className="text-fg-3">Not tested yet</span>
                        )}
                      </td>
                      <td className="px-3.5 py-2 text-right">
                        {m ? <Pct value={toNumber(m.totalReturn)} pnl dp={1} /> : ''}
                      </td>
                      <td className="num px-3.5 py-2 text-right text-fg-2">
                        {m?.benchmarkReturn
                          ? formatPct(toNumber(m.benchmarkReturn), { dp: 1, signed: true })
                          : ''}
                      </td>
                      <td className="num px-3.5 py-2 text-right text-loss">
                        {m ? formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1 }) : ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
