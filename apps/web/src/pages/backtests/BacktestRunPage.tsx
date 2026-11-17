import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { ArrowLeft, Download } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import {
  MonthByMonth,
  RunFailure,
  RunPanel,
  RunSections,
  RunSummary,
  useRunView,
} from '../../components/backtest';
import { csvRow, downloadText } from '../../components/backtest/files';
import { RunStatus } from '../../components/backtest/parts';
import { isFinished, runMeta, runSeconds, toTradeInputs } from '../../components/backtest/runData';
import { YearCurve } from '../../components/backtest/YearCurve';
import { DeploySheet } from '../../components/sessions/DeploySheet';
import { PageHead } from '../../components/ui/PageHead';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart, SkeletonFigure } from '../../components/ui/Skeleton';
import {
  dayKey,
  groupRebalances,
  latestTradedMonth,
  parseMonthHash,
  tradesToOrders,
} from '../../lib/backtestView';
import { formatMoney, formatNumber } from '../../lib/format';

/** /backtest/:runId: a finished run as a dense panel; #trades or #month-YYYY-MM for month by month. */
export default function BacktestRunPage() {
  const { runId = '' } = useParams();
  const { hash } = useLocation();
  const navigate = useNavigate();

  const run = useBacktestStore((s) => (s.currentBacktest?.id === runId ? s.currentBacktest : null));
  const loading = useBacktestStore((s) => s.loading);
  const error = useBacktestStore((s) => s.error);
  const getBacktest = useBacktestStore((s) => s.getBacktest);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const strategies = useBacktestStore((s) => s.strategies);
  const fullTrades = useBacktestStore((s) => s.fullTrades);
  const tradesLoading = useBacktestStore((s) => s.tradesLoading);
  const loadAllTrades = useBacktestStore((s) => s.loadAllTrades);
  const fetchVersionDsl = useBacktestStore((s) => s.fetchVersionDsl);

  const view = useRunView(run);
  const [dsl, setDsl] = useState<string | null | undefined>(undefined);
  const [deployOpen, setDeployOpen] = useState(false);
  const tradesFor = useRef<string | null>(null);

  const tradesView = hash === '#trades' || parseMonthHash(hash) !== null;
  const month = parseMonthHash(hash);

  useEffect(() => {
    fetchStrategies().catch(() => undefined);
  }, [fetchStrategies]);

  useEffect(() => {
    if (runId && !run) getBacktest(runId).catch(() => undefined);
  }, [runId, run, getBacktest]);

  // A run still in flight is watched on the setup page, where it fills in place.
  useEffect(() => {
    if (run && !isFinished(run.status)) navigate(`/backtest?run=${run.id}`, { replace: true });
  }, [run, navigate]);

  useEffect(() => {
    if (!run || run.status !== BacktestStatus.COMPLETED) return;
    setDsl(undefined);
    fetchVersionDsl(run.strategyId, run.strategyVersion)
      .then(setDsl)
      .catch(() => setDsl(null));
  }, [run, fetchVersionDsl]);

  useEffect(() => {
    if (!run || run.status !== BacktestStatus.COMPLETED) return;
    if (tradesFor.current === run.id) return;
    tradesFor.current = run.id;
    loadAllTrades(run.id).catch(() => undefined);
  }, [run, loadAllTrades]);

  const trades = useMemo(
    () =>
      fullTrades && tradesFor.current === runId && !tradesLoading
        ? toTradeInputs(fullTrades)
        : null,
    [fullTrades, tradesLoading, runId]
  );

  // #trades lands on the newest month that traded.
  useEffect(() => {
    if (hash !== '#trades' || !trades) return;
    const latest = latestTradedMonth(groupRebalances(tradesToOrders(trades)));
    if (latest) navigate({ hash: `month-${latest}` }, { replace: true });
  }, [hash, trades, navigate]);

  if (error && !run) {
    return (
      <div className="page grid gap-3.5">
        <Link
          to="/backtests"
          className="inline-flex items-center gap-1 justify-self-start text-[12.5px] text-accent hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Backtest history
        </Link>
        <div className="rounded-panel border border-line bg-panel">
          <PanelError
            title="This backtest couldn't be loaded"
            cause={error}
            onRetry={() => getBacktest(runId)}
            retrying={loading}
          />
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="page grid gap-3.5" aria-busy="true">
        <SkeletonFigure />
        <div className="rounded-panel border border-line bg-panel p-4">
          <SkeletonChart height={340} />
        </div>
      </div>
    );
  }

  const meta = runMeta(run);
  const name = `${view.strategyName} · version ${run.strategyVersion}`;
  const metaLine = (
    <span className="num">
      {meta.start ? dayKey(meta.start) : '·'} → {meta.end ? dayKey(meta.end) : '·'} ·{' '}
      {formatMoney(meta.capital, { dp: 0 })}
      {meta.benchmark ? ` · benchmark ${meta.benchmark}` : ''}
    </span>
  );
  const secs = runSeconds(run);
  const strategy = strategies.find((s) => s.id === run.strategyId);
  const completed = view.phase === 'completed';

  const exportCsv = async () => {
    if (!fullTrades || tradesFor.current !== run.id) {
      tradesFor.current = run.id;
      await loadAllTrades(run.id);
    }
    const all = toTradeInputs(useBacktestStore.getState().fullTrades ?? []);
    const lines = [
      csvRow(['date', 'side', 'symbol', 'quantity', 'price', 'value', 'pnl', 'reason']),
      ...tradesToOrders(all).map((o) =>
        csvRow([
          o.date,
          o.side,
          o.symbol,
          o.quantity,
          o.price.toFixed(4),
          o.value.toFixed(2),
          o.pnl?.toFixed(2) ?? '',
          o.reason,
        ])
      ),
    ];
    downloadText(
      `${view.strategyName.replace(/\W+/g, '-').toLowerCase()}-v${run.strategyVersion}-orders.csv`,
      lines.join('\n')
    );
  };

  if (tradesView && completed) {
    const orderCount = trades ? tradesToOrders(trades).length : null;
    const rebalanceCount = trades ? groupRebalances(tradesToOrders(trades)).length : null;
    return (
      <div className="page grid gap-3.5">
        <Link
          to={`/backtest/${run.id}`}
          className="inline-flex items-center gap-1 justify-self-start text-[12.5px] text-accent hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to results
        </Link>
        <PageHead
          title={`${view.strategyName} · trades and monthly returns`}
          sub={
            orderCount === null
              ? 'Loading the orders…'
              : `${formatNumber(orderCount, { dp: 0 })} simulated orders over ${formatNumber(rebalanceCount ?? 0, { dp: 0 })} rebalances · pick a month`
          }
          actions={
            <button type="button" className="btn btn-secondary" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              CSV
            </button>
          }
        />
        <YearCurve
          run={run}
          trades={trades}
          month={month}
          strategyName={view.strategyName}
          onMonth={(m) => navigate({ hash: `month-${m}` }, { replace: true })}
        />
        <MonthByMonth
          run={run}
          trades={trades}
          month={month}
          onMonth={(m) => navigate({ hash: `month-${m}` }, { replace: true })}
        />
      </div>
    );
  }

  return (
    <div className="page grid gap-3.5">
      <PageHead
        title={name}
        sub={metaLine}
        actions={
          <>
            <RunStatus
              phase={view.phase}
              label={
                completed && secs !== null
                  ? `Completed in ${formatNumber(secs, { dp: 1 })} s`
                  : view.phase === 'failed'
                    ? 'Failed'
                    : undefined
              }
            />
            {completed && (
              <button type="button" className="btn btn-secondary" onClick={exportCsv}>
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                Export
              </button>
            )}
            <Link to={`/backtest?rerun=${run.id}`} className="btn btn-secondary">
              Run again
            </Link>
            {completed && (
              <button type="button" className="btn btn-primary" onClick={() => setDeployOpen(true)}>
                Deploy to paper
              </button>
            )}
          </>
        }
      />
      {completed && <RunSummary run={run} strategyName={view.strategyName} />}
      <RunPanel
        run={run}
        phase={view.phase}
        log={view.log}
        partial={view.partial}
        progress={view.progress}
        currentDate={view.currentDate}
        strategyName={view.strategyName}
        rebalance={view.rebalance}
        trades={trades}
        failure={
          view.phase === 'failed' || view.phase === 'cancelled' ? (
            <RunFailure
              phase={view.phase}
              message={run.statusMessage}
              strategyId={run.strategyId}
              onBack={() => navigate('/backtest')}
              run={run}
            />
          ) : undefined
        }
      />
      {completed && (
        <RunSections run={run} dsl={dsl} onOpenTrades={() => navigate({ hash: 'trades' })} />
      )}
      {completed && (
        <DeploySheet
          open={deployOpen}
          onClose={() => setDeployOpen(false)}
          strategyId={run.strategyId}
          strategyName={view.strategyName}
          strategyVersion={run.strategyVersion}
          rebalance={strategy?.rebalance}
          context="from this backtest · Alpaca paper"
          suggestedCapital={meta.capital}
        />
      )}
    </div>
  );
}
