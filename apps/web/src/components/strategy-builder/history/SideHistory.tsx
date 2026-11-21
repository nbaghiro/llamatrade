import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { rangeLabel } from '../../../lib/backtestView';
import { formatPct } from '../../../lib/format';
import { AnnotatedCurve, type CurveBand, type CurveLane } from '../../charts';
import { Pct, StatList } from '../../ui';
import type { RebalanceEvery } from '../blocks/conditionHistory';

import { shortCondition, sideHistoryView } from './sideHistoryView';
import type { SideKey } from './sides';

interface SideHistoryProps {
  run: BacktestRun;
  /** The rules the lanes are read against: the saved version's tree. */
  tree: StrategyTree;
  every: RebalanceEvery;
  /** The side whose rule is selected in the outline, drawn lit. */
  lit?: SideKey | null;
}

/** blocks2 A: the last backtest's curve, with a lane for each side of the condition. */
export function SideHistory({ run, tree, every, lit = null }: SideHistoryProps) {
  const view = useMemo(() => sideHistoryView(run, tree, every), [run, tree, every]);

  if (!view) return null;
  const { totalReturn, benchReturn, counts } = view;
  const bench = view.benchSymbol;

  const bands: CurveBand[] = view.spans
    .filter((s) => s.side === 'when')
    .map((s) => ({ from: s.from, to: s.to, tone: 'held', through: true }));

  const lanes: CurveLane[] = [];
  if (view.sides) {
    lanes.push(
      {
        id: 'when',
        label: `When ${shortCondition(view.sides.condition)}`,
        value: (
          <span className="num text-[11.5px] text-fg-3">
            {counts.when} of {counts.known}
          </span>
        ),
        tone: lit === 'when' ? 'default' : 'muted',
        spans: view.spans
          .filter((s) => s.side === 'when')
          .map((s) => ({
            from: s.from,
            to: s.to,
            style: 'bar' as const,
            ...(lit === 'when' ? {} : { tone: 'muted' as const }),
          })),
      },
      {
        id: 'otherwise',
        label: 'Otherwise',
        value: (
          <span className="num text-[11.5px] text-fg-3">
            {counts.otherwise} of {counts.known}
          </span>
        ),
        tone: lit === 'when' ? 'muted' : 'default',
        spans: view.spans
          .filter((s) => s.side === 'otherwise')
          .map((s) => ({ from: s.from, to: s.to, style: 'bar' as const })),
      }
    );
  }
  lanes.push({
    id: 'rebalances',
    label: view.scheduled ? 'Rebalances' : 'Days with orders',
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
            {totalReturn !== null && <Pct value={totalReturn} pnl dp={1} />}
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
        dates={view.dates}
        values={view.values}
        benchmark={view.benchmark}
        bands={bands}
        lanes={lanes}
        height={150}
        side={
          view.maxDrawdown !== null && view.sharpe !== null ? (
            <StatList
              items={[
                {
                  label: 'Max drawdown',
                  value: formatPct(view.maxDrawdown, { dp: 1, signed: true }),
                },
                { label: 'Sharpe', value: view.sharpe.toFixed(2) },
              ]}
            />
          ) : undefined
        }
      />
      <p className="m-0 mt-2 text-[12px] text-fg-3">
        {view.sides
          ? `Each side is read from what the backtest held at the end of ${view.scheduled ? 'each scheduled rebalance' : 'each day it traded'}${counts.unknown > 0 ? `; ${counts.unknown} held a mix or nothing and ${counts.unknown === 1 ? 'is' : 'are'} left out` : ''}. These lanes describe version ${run.strategyVersion} until a newer version is backtested.`
          : `The rules don't split into two sides that hold different symbols, so only the days with orders are drawn.`}
      </p>
    </section>
  );
}
