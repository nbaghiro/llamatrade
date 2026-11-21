import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { formatPct } from '../../../lib/format';
import { AnnotatedCurve, type CurveLane } from '../../charts';
import { Pct } from '../../ui';
import type { RebalanceEvery } from '../blocks/conditionHistory';
import { shortCondition, sideHistoryView } from '../history/sideHistoryView';
import type { SideKey } from '../history/sides';
import { KeyValue } from '../rail/RailPanel';

export interface SplitHistory {
  run: BacktestRun;
  tree: StrategyTree;
  every: RebalanceEvery;
  lit: SideKey | null;
  /** True when the draft differs from the saved version the lanes describe. */
  dirty: boolean;
}

/** split2 C: a narrow "When each side held" pane beside the rules and the code. */
export function SplitHistoryStrip({ run, tree, every, lit, dirty }: SplitHistory) {
  const view = useMemo(() => sideHistoryView(run, tree, every), [run, tree, every]);
  const version = run.strategyVersion;

  const head = (
    <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
      <h3 className="m-0 text-[13px] font-semibold text-fg">When each side held</h3>
      <Link
        to={`/backtest/${run.id}`}
        className="rounded-[4px] border border-dashed border-line-strong px-1.5 py-px font-mono text-[11px] text-fg-2 hover:text-fg"
      >
        Backtest · v{version}
      </Link>
    </header>
  );

  if (!view) {
    return (
      <section className="panel min-w-0 overflow-hidden" aria-label="When each side held">
        {head}
        <p className="m-0 px-4 py-4 text-[12.5px] text-fg-2">
          This backtest has no curve to draw yet.
        </p>
      </section>
    );
  }

  const lanes: CurveLane[] = view.sides
    ? (['when', 'otherwise'] as const).map((side) => ({
        id: side,
        label: side === 'when' && view.sides ? shortCondition(view.sides.condition) : 'Otherwise',
        tone: lit && lit !== side ? 'muted' : 'default',
        spans: view.spans
          .filter((s) => s.side === side)
          .map((s) => ({
            from: s.from,
            to: s.to,
            style: 'bar' as const,
            ...(side === 'when' && lit !== 'when' ? { tone: 'muted' as const } : {}),
          })),
      }))
    : [];

  const scheduleWords = view.scheduled ? `${every} rebalances` : 'days with orders';
  return (
    <section
      className={`panel min-w-0 overflow-hidden ${lit ? 'panel-rim' : ''}`}
      aria-label="When each side held"
    >
      {head}
      <div className="px-3 pt-3">
        <AnnotatedCurve
          label={`Backtest of version ${version}, with the side held at each rebalance`}
          dates={view.dates}
          values={view.values}
          benchmark={view.benchmark}
          lanes={lanes}
          height={96}
          labelWidth={92}
        />
      </div>
      <div className="px-4 pb-3">
        {view.sides && (
          <KeyValue
            k="When side held"
            v={
              <span className="num">
                {view.counts.when} of {view.counts.known} {scheduleWords}
              </span>
            }
          />
        )}
        {view.totalReturn !== null && (
          <KeyValue
            k="Return"
            v={
              <span className="num">
                <Pct value={view.totalReturn} pnl dp={1} />
                {view.benchReturn !== null &&
                  ` · ${view.benchSymbol} ${formatPct(view.benchReturn, { dp: 1, signed: true })}`}
              </span>
            }
          />
        )}
        {view.maxDrawdown !== null && (
          <KeyValue
            k="Max drawdown"
            v={<span className="num">{formatPct(view.maxDrawdown, { dp: 1, signed: true })}</span>}
          />
        )}
        <p className="m-0 pt-2.5 text-[12px] leading-[1.55] text-fg-3">
          {view.sides
            ? `These lanes describe version ${version} as saved.`
            : `The rules don't split into two sides that hold different symbols, so no lanes are drawn.`}
          {dirty && ' Save and backtest the draft to see how your changes move them.'}
        </p>
      </div>
    </section>
  );
}
