import {
  BacktestStatus,
  type BacktestMetrics,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { useNavigate } from 'react-router-dom';

import { formatNumber } from '../../lib/format';
import { Pct } from '../ui/Num';

import { RunStatus } from './parts';
import { phaseOf } from './runData';
import { runRange, runWhen, strategyNameOf } from './runLabels';
import { T } from './tableStyles';

interface HistoryTableProps {
  runs: readonly BacktestRun[];
  metrics: Readonly<Record<string, BacktestMetrics>>;
  strategies: readonly Strategy[];
  /** Shows tick boxes for completed runs when set. */
  selected?: readonly string[];
  onToggle?: (id: string) => void;
  compact?: boolean;
}

/** Backtest runs, newest first, with their state and headline figures. */
export function HistoryTable({
  runs,
  metrics,
  strategies,
  selected,
  onToggle,
  compact = false,
}: HistoryTableProps) {
  const navigate = useNavigate();
  const selectable = Boolean(onToggle && selected);
  const dot = <span className="text-fg-3">·</span>;
  return (
    <div className="overflow-x-auto">
      <table className={T.table}>
        <thead>
          <tr>
            {selectable && (
              <th className={`${T.th} w-[30px]`}>
                <span className="sr-only">Select to compare</span>
              </th>
            )}
            <th className={T.th}>Strategy</th>
            <th className={T.th}>Run</th>
            {!compact && <th className={T.th}>Range</th>}
            <th className={T.thN}>Return</th>
            {!compact && <th className={T.thN}>Max drawdown</th>}
            {!compact && <th className={T.thN}>Sharpe</th>}
            <th className={T.th}>State</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const m = metrics[r.id];
            const done = r.status === BacktestStatus.COMPLETED;
            const on = selected?.includes(r.id) ?? false;
            const name = strategyNameOf(strategies, r.strategyId);
            return (
              <tr
                key={r.id}
                onClick={() => navigate(`/backtest/${r.id}`)}
                className={`cursor-pointer hover:bg-sunk ${on ? T.rowSel : ''}`}
              >
                {selectable && (
                  <td className={T.td} onClick={(e) => e.stopPropagation()}>
                    {done && (
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => onToggle?.(r.id)}
                        aria-label={`Compare ${name} version ${r.strategyVersion}`}
                        className="h-3.5 w-3.5 accent-[rgb(var(--accent-fill))]"
                      />
                    )}
                  </td>
                )}
                <td className={`${T.td} ${compact ? '' : 'h-11'}`}>
                  <b className="font-semibold">{name}</b>
                  <span className={T.sub}>version {r.strategyVersion}</span>
                </td>
                <td className={`${T.td} num text-fg-2`}>{runWhen(r)}</td>
                {!compact && <td className={`${T.td} num text-fg-2`}>{runRange(r)}</td>}
                <td className={T.tdN}>
                  {done && m ? <Pct value={toNumber(m.totalReturn)} pnl dp={1} /> : dot}
                </td>
                {!compact && (
                  <td className={T.tdN}>
                    {done && m ? (
                      <Pct value={-Math.abs(toNumber(m.maxDrawdown))} pnl dp={1} />
                    ) : (
                      dot
                    )}
                  </td>
                )}
                {!compact && (
                  <td className={T.tdN}>
                    {done && m ? formatNumber(toNumber(m.sharpeRatio), { dp: 2 }) : dot}
                  </td>
                )}
                <td className={T.td}>
                  <RunStatus phase={phaseOf(r.status)} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
