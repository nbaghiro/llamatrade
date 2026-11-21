import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatNumber } from '../../lib/format';
import { KvList, Panel } from '../backtest/parts';
import { toCurve } from '../backtest/runData';
import { Sparkline } from '../charts';
import { PaperPill } from '../shell/PaperPill';
import { Pct } from '../ui/Num';
import { SkeletonRows } from '../ui/Skeleton';

import { DeploySheet } from './DeploySheet';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** The newest completed run of each strategy, newest first. */
function latestPerStrategy(runs: readonly BacktestRun[]): BacktestRun[] {
  const seen = new Set<string>();
  return runs.filter((r) => {
    if (seen.has(r.strategyId)) return false;
    seen.add(r.strategyId);
    return true;
  });
}

/** Sessions before the first deploy: strategies with a completed backtest, each one click from paper. */
export function ReadyToDeploy() {
  const recentRuns = useBacktestStore((s) => s.recentRuns);
  const loading = useBacktestStore((s) => s.recentRunsLoading);
  const fetchRecentRuns = useBacktestStore((s) => s.fetchRecentRuns);
  const strategies = useBacktestStore((s) => s.strategies);
  const resolveAccount = useFundingStore((s) => s.resolveAccount);
  const resolved = useFundingStore((s) => s.resolved);
  const unallocated = useFundingStore((s) => s.unallocatedCash);
  const credentialId = useFundingStore((s) => s.paperCredentialId);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [deploying, setDeploying] = useState<BacktestRun | null>(null);

  useEffect(() => {
    fetchRecentRuns(24)
      .catch(() => undefined)
      .finally(() => setLoadedOnce(true));
    resolveAccount().catch(() => undefined);
  }, [fetchRecentRuns, resolveAccount]);

  const ready = useMemo(() => latestPerStrategy(recentRuns), [recentRuns]);
  const strategyOf = (r: BacktestRun) => strategies.find((s) => s.id === r.strategyId);
  const runDate = (r: BacktestRun) => {
    const d = toDate(r.completedAt) ?? toDate(r.createdAt);
    return d ? `${MON[d.getMonth()]} ${d.getDate()}` : '·';
  };

  return (
    <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <Panel
        title="Ready to start"
        aside="strategies with a completed backtest"
        footer={
          <span className="flex justify-between gap-3">
            <span>Strategies without a backtest need one first.</span>
            <Link to="/strategies" className="text-accent hover:underline">
              All strategies
            </Link>
          </span>
        }
      >
        {!loadedOnce || (loading && !ready.length) ? (
          <SkeletonRows rows={3} cols={5} />
        ) : ready.length === 0 ? (
          <div className="grid justify-items-start gap-2 px-4 py-5">
            <p className="m-0 text-[13px] text-fg-2">
              No strategy has a completed backtest yet. Run one to see how it would have done, then
              start it from its results.
            </p>
            <Link to="/backtest" className="btn btn-primary">
              Set up a backtest
            </Link>
          </div>
        ) : (
          <>
            <div
              aria-hidden="true"
              className="hidden gap-x-3.5 border-b border-line px-4 py-2 text-[11px] font-medium text-fg-3 md:grid md:grid-cols-[minmax(0,1fr)_80px_64px_88px_120px_132px]"
            >
              <span>Strategy</span>
              <span>Last backtest</span>
              <span className="text-right">Sharpe</span>
              <span className="text-right">Max drawdown</span>
              <span />
              <span />
            </div>
            <ul className="m-0 list-none p-0">
              {ready.map((r, i) => {
                const s = strategyOf(r);
                const m = r.results?.metrics;
                const curve = toCurve(r.results?.equityCurve).values;
                return (
                  <li
                    key={r.id}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3.5 gap-y-2 border-b border-line px-4 py-3.5 text-[12.5px] last:border-b-0 md:grid-cols-[minmax(0,1fr)_80px_64px_88px_120px_132px]"
                  >
                    <span className="min-w-0">
                      <Link
                        to={`/backtest/${r.id}`}
                        className="block truncate font-semibold hover:underline"
                      >
                        {s?.name ?? 'Strategy'}
                      </Link>
                      <span className="block text-[11px] text-fg-3">
                        version {r.strategyVersion}
                        {s?.rebalance ? ` · ${s.rebalance.toLowerCase()}` : ''} · run {runDate(r)}
                      </span>
                    </span>
                    <span className="text-right md:text-left">
                      <span className="sr-only">Last backtest return </span>
                      {m ? <Pct value={toNumber(m.totalReturn)} pnl dp={1} /> : '·'}
                    </span>
                    <span className="num hidden text-right md:block" title="Sharpe">
                      <span className="sr-only">Sharpe </span>
                      {m ? formatNumber(toNumber(m.sharpeRatio), { dp: 2 }) : '·'}
                    </span>
                    <span className="hidden text-right md:block" title="Max drawdown">
                      <span className="sr-only">Max drawdown </span>
                      {m ? <Pct value={-Math.abs(toNumber(m.maxDrawdown))} dp={1} /> : '·'}
                    </span>
                    <span className="hidden md:block">
                      <Sparkline
                        values={curve}
                        width={120}
                        height={28}
                        label={`${s?.name ?? 'Strategy'} equity`}
                      />
                    </span>
                    <span className="col-span-2 md:col-span-1 md:text-right">
                      <button
                        type="button"
                        className={`btn w-full md:w-auto ${i === 0 ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setDeploying(r)}
                      >
                        Start on paper
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </Panel>
      <div className="grid gap-3.5">
        <Panel title="Paper account" aside={<PaperPill />}>
          <div className="px-3.5 py-1">
            <KvList
              rows={[
                ['Alpaca paper', !resolved ? '·' : credentialId ? 'connected' : 'not connected'],
                [
                  'Unallocated',
                  <span key="u" className="num">
                    {resolved ? formatMoney(unallocated) : '·'}
                  </span>,
                ],
                [
                  'In sessions',
                  <span key="s" className="num">
                    {formatMoney(0)}
                  </span>,
                ],
              ]}
            />
          </div>
        </Panel>
        <Panel title="What a session does">
          <ul className="m-0 grid list-none gap-2 px-3.5 py-3 text-[12.5px] text-fg-2">
            <li>Moves the capital you choose into a sleeve for that strategy.</li>
            <li>
              Rebalances on the strategy&apos;s schedule, sending each order through seven risk
              checks.
            </li>
            <li>Reconciles with Alpaca so the ledger and the broker agree.</li>
          </ul>
        </Panel>
      </div>
      {deploying && (
        <DeploySheet
          open
          onClose={() => setDeploying(null)}
          strategyId={deploying.strategyId}
          strategyName={strategyOf(deploying)?.name ?? 'Strategy'}
          strategyVersion={deploying.strategyVersion}
          rebalance={strategyOf(deploying)?.rebalance}
          context="from its latest backtest · Alpaca paper"
          suggestedCapital={toNumber(deploying.config?.initialCapital)}
        />
      )}
    </div>
  );
}
