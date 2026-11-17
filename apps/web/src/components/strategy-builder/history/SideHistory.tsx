import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { alignTo, rangeLabel } from '../../../lib/backtestView';
import { formatPct } from '../../../lib/format';
import { toCurve, toTradeInputs } from '../../backtest/runData';
import { AnnotatedCurve, type CurveBand, type CurveLane } from '../../charts';
import { StatList } from '../../ui';

import { conditionSides, sideSpans, sidesAtRebalances } from './sides';

interface SideHistoryProps {
  run: BacktestRun;
  /** The rules the lanes are read against: the saved version's tree. */
  tree: StrategyTree;
  /** True while the condition the lanes describe is selected in the outline. */
  lit?: boolean;
}

/** blocks2 A: the last backtest's curve, with a lane for each side of the condition. */
export function SideHistory({ run, tree, lit = false }: SideHistoryProps) {
  const view = useMemo(() => {
    const curve = toCurve(run.results?.equityCurve);
    if (curve.dates.length < 2) return null;
    const benchCurve = toCurve(run.results?.benchmarkEquityCurve);
    const aligned = benchCurve.dates.length ? alignTo(curve.dates, benchCurve) : [];
    const firstBench = aligned.find((v): v is number => v !== null);
    const benchmark =
      firstBench !== undefined
        ? aligned.map((v) => ((v ?? firstBench) / firstBench) * curve.values[0])
        : undefined;
    const start = curve.dates[0];
    const end = curve.dates[curve.dates.length - 1];
    const trades = toTradeInputs(run.results?.trades ?? []);
    const sides = conditionSides(tree);
    const points = sides ? sidesAtRebalances(trades, sides) : [];
    const rebalanceDates = sides
      ? points.map((p) => p.date)
      : [
          ...new Set(
            trades
              .flatMap((t) => [t.entryTime, t.exitTime])
              .flatMap((d) => (d ? [d.getTime()] : []))
          ),
        ]
          .sort((a, b) => a - b)
          .map((t) => new Date(t));
    const spans = sides ? sideSpans(points, end) : [];
    const known = points.filter((p) => p.side !== null).length;
    const whenCount = points.filter((p) => p.side === 'when').length;
    const otherCount = points.filter((p) => p.side === 'otherwise').length;
    return {
      curve,
      benchmark,
      start,
      end,
      sides,
      spans,
      rebalanceDates,
      known,
      whenCount,
      otherCount,
      unknown: points.length - known,
    };
  }, [run, tree]);

  if (!view) return null;
  const m = run.results?.metrics;
  const totalReturn = m ? toNumber(m.totalReturn) : null;
  const benchReturn = m ? toNumber(m.benchmarkReturn) : null;
  const bench = run.results?.benchmarkSymbol || run.config?.benchmarkSymbol || 'Benchmark';

  const bands: CurveBand[] = view.spans
    .filter((s) => s.side === 'when')
    .map((s) => ({ from: s.from, to: s.to, tone: 'held', through: true }));

  const lanes: CurveLane[] = [];
  if (view.sides) {
    lanes.push(
      {
        id: 'when',
        label: `When ${view.sides.condition}`,
        value: (
          <span className="num text-[11.5px] text-fg-3">
            {view.whenCount} of {view.known}
          </span>
        ),
        tone: lit ? 'default' : 'muted',
        spans: view.spans
          .filter((s) => s.side === 'when')
          .map((s) => ({ from: s.from, to: s.to, style: 'bar' as const, tone: 'muted' as const })),
      },
      {
        id: 'otherwise',
        label: 'Otherwise',
        value: (
          <span className="num text-[11.5px] text-fg-3">
            {view.otherCount} of {view.known}
          </span>
        ),
        spans: view.spans
          .filter((s) => s.side === 'otherwise')
          .map((s) => ({ from: s.from, to: s.to, style: 'bar' as const })),
      }
    );
  }
  lanes.push({
    id: 'rebalances',
    label: 'Days with orders',
    value: <span className="num text-[11.5px] text-fg-3">{view.rebalanceDates.length}</span>,
    spans: [],
    events: view.rebalanceDates.map((at) => ({ at, shape: 'start' as const })),
  });

  return (
    <section
      aria-label="When each side held"
      className={`panel px-5 pb-2 pt-4 ${lit ? 'panel-rim' : ''}`}
    >
      <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h3 className="m-0 text-[13.5px] font-semibold text-fg">
          {view.sides ? 'When each side held' : 'Last backtest'}
        </h3>
        <Link
          to={`/backtest/${run.id}`}
          className="rounded-[4px] border border-dashed border-line-strong px-1.5 py-px font-mono text-[11px] text-fg-2 hover:text-fg"
        >
          Backtest · version {run.strategyVersion}
        </Link>
        <span className="font-mono text-[11.5px] text-fg-3">
          {rangeLabel(view.start, view.end)}
        </span>
        <span className="ml-auto flex items-center gap-4 text-[11.5px] text-fg-2">
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-[2px] w-4 bg-accent" aria-hidden="true" />
            Version {run.strategyVersion}
            {totalReturn !== null && (
              <span className="num text-gain">
                {formatPct(totalReturn, { dp: 1, signed: true })}
              </span>
            )}
          </span>
          {view.benchmark && (
            <span className="flex items-center gap-1.5">
              <i
                className="inline-block h-0 w-4 border-t border-dashed border-fg-3"
                aria-hidden="true"
              />
              {bench}
              {benchReturn !== null && (
                <span className="num">{formatPct(benchReturn, { dp: 1, signed: true })}</span>
              )}
            </span>
          )}
        </span>
      </header>
      <AnnotatedCurve
        label={`Backtest of version ${run.strategyVersion}, with the side held on each day it traded`}
        dates={view.curve.dates}
        values={view.curve.values}
        benchmark={view.benchmark}
        bands={bands}
        lanes={lanes}
        height={150}
        side={
          m ? (
            <StatList
              items={[
                {
                  label: 'Max drawdown',
                  value: formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1, signed: true }),
                  tone: 'loss',
                },
                { label: 'Sharpe', value: toNumber(m.sharpeRatio).toFixed(2) },
              ]}
            />
          ) : undefined
        }
      />
      <p className="m-0 mt-2 text-[12px] text-fg-3">
        {view.sides
          ? `Each side is read from what the backtest held at the end of each day it traded${view.unknown > 0 ? `; ${view.unknown} ${view.unknown === 1 ? 'day held' : 'days held'} a mix and ${view.unknown === 1 ? 'is' : 'are'} left out` : ''}. These lanes describe version ${run.strategyVersion} until a newer version is backtested.`
          : `The rules don't split into two sides that hold different symbols, so only the days with orders are drawn.`}
      </p>
    </section>
  );
}
