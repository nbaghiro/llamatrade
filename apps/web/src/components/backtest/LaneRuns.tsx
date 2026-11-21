import {
  BacktestStatus,
  type BacktestMetrics,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { Columns2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { formatNumber, formatPct } from '../../lib/format';
import { Pct } from '../ui/Num';

import type { NewerThanTrading } from './historyLanes';
import { RunStatus } from './parts';
import { phaseOf } from './runData';
import { runRange, runWhen } from './runLabels';
import type { StrategySession } from './strategySessions';
import { T } from './tableStyles';

/** One strategy's runs, newest first, tagging the version its session trades (history2 A). */
export function LaneRunTable({
  runs,
  metrics,
  session,
}: {
  runs: readonly BacktestRun[];
  metrics: Readonly<Record<string, BacktestMetrics>>;
  session: StrategySession | null;
}) {
  const navigate = useNavigate();
  const dot = <span className="text-fg-3">·</span>;
  return (
    <div className="overflow-x-auto">
      <table className={T.table}>
        <thead>
          <tr>
            <th className={T.th}>Run</th>
            <th className={T.th}>Range</th>
            <th className={T.th}>Ran</th>
            <th className={T.thN}>Return</th>
            <th className={T.thN}>SPY</th>
            <th className={T.thN}>Sharpe</th>
            <th className={T.thN}>Max drawdown</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const m = metrics[r.id];
            const done = r.status === BacktestStatus.COMPLETED && m;
            const trades =
              session?.active && session.version === r.strategyVersion ? session : null;
            const running =
              r.status === BacktestStatus.RUNNING || r.status === BacktestStatus.PENDING;
            return (
              <tr
                key={r.id}
                onClick={() => navigate(running ? `/backtest?run=${r.id}` : `/backtest/${r.id}`)}
                className={`cursor-pointer hover:bg-sunk ${trades ? T.rowSel : ''}`}
              >
                <td className={`${T.td} h-10`}>
                  <b className="font-mono font-semibold">v{r.strategyVersion}</b>
                  {trades && (
                    <span className="ml-1.5 text-[11px] text-fg-3">· {trades.mode} session</span>
                  )}
                </td>
                <td className={`${T.td} num text-fg-2`}>{runRange(r)}</td>
                <td className={`${T.td} num text-fg-2`}>{runWhen(r)}</td>
                {done ? (
                  <>
                    <td className={T.tdN}>
                      <Pct value={toNumber(m.totalReturn)} pnl dp={1} />
                    </td>
                    <td className={T.tdN}>
                      {m.benchmarkReturn
                        ? formatPct(toNumber(m.benchmarkReturn), { dp: 1, signed: true })
                        : dot}
                    </td>
                    <td className={T.tdN}>{formatNumber(toNumber(m.sharpeRatio), { dp: 2 })}</td>
                    <td className={T.tdN}>
                      {formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1 })}
                    </td>
                  </>
                ) : (
                  <td className={T.td} colSpan={4}>
                    <span className="flex justify-end">
                      {running ? (
                        <RunStatus
                          phase="running"
                          label={`Running · ${formatNumber(r.progressPercent, { dp: 0 })}%${
                            r.currentDate ? `, through ${r.currentDate}` : ''
                          }`}
                        />
                      ) : (
                        <RunStatus phase={phaseOf(r.status)} />
                      )}
                    </span>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** "Newer than what's trading": a newer version backtested than the active session runs. */
export function NewerCallout({ newer, name }: { newer: NewerThanTrading; name: string }) {
  const n = newer.newer.run;
  const t = newer.trading?.run ?? null;
  const running = n.status !== BacktestStatus.COMPLETED;
  const ses = newer.session;
  const first = running
    ? `${name} v${n.strategyVersion} is being backtested now.`
    : `${name} v${n.strategyVersion} has a finished backtest.`;
  const second =
    newer.points !== null
      ? ` It returned ${formatNumber(Math.abs(newer.points), { dp: 1 })} pts ${newer.points >= 0 ? 'more' : 'less'} than v${ses.version} on the same settings.`
      : '';
  const third = ` The ${ses.mode} session runs v${ses.version}.`;
  return (
    <section className="panel-rim min-w-0 overflow-hidden">
      <h2 className="m-0 border-b border-line px-3.5 py-2.5 text-[12.5px] font-semibold">
        Newer than what&apos;s trading
      </h2>
      <div className="grid gap-3 px-3.5 py-3 text-[12.5px] leading-[1.55] text-fg-2">
        <p className="m-0">
          {first}
          {second}
          {third}
        </p>
        <span className="flex flex-wrap gap-2">
          {!running && t && (
            <Link to={`/backtests/compare?runs=${t.id},${n.id}`} className="btn btn-secondary">
              <Columns2 className="h-3.5 w-3.5" aria-hidden="true" />
              Compare v{t.strategyVersion} and v{n.strategyVersion}
            </Link>
          )}
          {running && (
            <Link to={`/backtest?run=${n.id}`} className="btn btn-secondary">
              Watch the run
            </Link>
          )}
          {ses.href && (
            <Link to={ses.href} className="btn btn-ghost">
              Open the {ses.mode} session
            </Link>
          )}
        </span>
      </div>
    </section>
  );
}
