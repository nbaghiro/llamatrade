import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { ArrowLeft, Columns2, Download, RotateCw } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { MonthByMonth, RunFailure, RunPanel, useRunView } from '../../components/backtest';
import { csvRow, downloadText } from '../../components/backtest/files';
import { RunStatus } from '../../components/backtest/parts';
import {
  previousVersionRun,
  resultMetaLine,
  untestedRange,
} from '../../components/backtest/resultLinks';
import { ResultView } from '../../components/backtest/ResultView';
import { isFinished, runMeta, runSeconds, toTradeInputs } from '../../components/backtest/runData';
import { stoppedStage } from '../../components/backtest/runSteps';
import { openSessionLabel, sessionForVersion } from '../../components/backtest/strategySessions';
import { useStrategySessions } from '../../components/backtest/useStrategySessions';
import { DeploySheet } from '../../components/sessions/DeploySheet';
import { PageHead } from '../../components/ui/PageHead';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart, SkeletonFigure } from '../../components/ui/Skeleton';
import type { CuratedRange } from '../../lib/backtestRanges';
import {
  groupRebalances,
  latestTradedMonth,
  parseMonthHash,
  tradesToOrders,
} from '../../lib/backtestView';
import { formatNumber } from '../../lib/format';

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
  const history = useBacktestStore((s) => s.history);
  const loadHistory = useBacktestStore((s) => s.loadHistory);
  const setConfig = useBacktestStore((s) => s.setConfig);

  const view = useRunView(run);
  const { sessions: sessionList } = useStrategySessions();
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
    if (!history.loaded && !history.loading) loadHistory().catch(() => undefined);
  }, [history.loaded, history.loading, loadHistory]);

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
  const completed = view.phase === 'completed';
  const stopNote =
    view.phase === 'failed' && run.progressPercent > 0
      ? ` · stopped at ${formatNumber(run.progressPercent, { dp: 0 })}%, ${stoppedStage(run.progressPercent)}`
      : '';
  const metaLine = (
    <span className="num">
      {resultMetaLine(run, completed)}
      {stopNote}
    </span>
  );
  const secs = runSeconds(run);
  const strategy = strategies.find((s) => s.id === run.strategyId);
  const session = sessionForVersion(sessionList, run.strategyId, run.strategyVersion);
  const compareWith = previousVersionRun(history.runs, run);
  const next = completed ? untestedRange(history.runs, run, new Date()) : null;
  const testRange = (range: CuratedRange) => {
    setConfig({
      strategyId: run.strategyId,
      strategyVersion: run.strategyVersion,
      startDate: range.start,
      endDate: range.end,
      initialCapital: meta.capital,
      ...(meta.benchmark ? { benchmarkSymbol: meta.benchmark } : {}),
    });
    navigate('/backtest');
  };

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
    return (
      <div className="page grid gap-3.5">
        <Link
          to={`/backtest/${run.id}`}
          className="inline-flex items-center gap-1 justify-self-start text-[12.5px] text-accent hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to results
        </Link>
        <MonthByMonth
          run={run}
          trades={trades}
          month={month}
          strategyName={view.strategyName}
          onMonth={(m: string) => navigate({ hash: `month-${m}` }, { replace: true })}
          actions={
            <button type="button" className="btn btn-secondary" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              CSV
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="page grid gap-3.5">
      <PageHead
        title={view.strategyName}
        documentTitle={`${view.strategyName} v${run.strategyVersion} backtest`}
        badges={
          <>
            <span className="rounded border border-line-strong px-1.5 py-px font-mono text-[11px] text-fg-2">
              v{run.strategyVersion}
            </span>
            <span className="text-[12px] text-fg-3">Backtest</span>
          </>
        }
        sub={metaLine}
        actions={
          <>
            {!completed && (
              <RunStatus
                phase={view.phase}
                label={view.phase === 'failed' ? "Couldn't finish" : undefined}
              />
            )}
            {completed && compareWith && (
              <Link
                to={`/backtests/compare?runs=${run.id},${compareWith.id}`}
                className="btn btn-secondary"
              >
                <Columns2 className="h-3.5 w-3.5" aria-hidden="true" />
                Compare
              </Link>
            )}
            {completed && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={exportCsv}
                title={
                  secs !== null ? `Completed in ${formatNumber(secs, { dp: 1 })} s` : undefined
                }
              >
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                Export
              </button>
            )}
            {!completed && (
              <Link to={`/backtest?rerun=${run.id}`} className="btn btn-secondary">
                Edit settings
              </Link>
            )}
            <Link
              to={`/backtest?rerun=${run.id}`}
              className={completed ? 'btn btn-secondary' : 'btn btn-primary'}
            >
              <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
              Run again
            </Link>
            {completed &&
              (session?.href ? (
                <Link to={session.href} className="btn btn-primary">
                  {openSessionLabel(session)}
                </Link>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setDeployOpen(true)}
                >
                  Start on paper
                </button>
              ))}
          </>
        }
      />
      {completed ? (
        <ResultView
          run={run}
          strategyName={view.strategyName}
          trades={trades}
          rebalance={view.rebalance}
          session={session}
          next={next}
          onNext={testRange}
          onOpenTrades={() => navigate({ hash: 'trades' })}
        />
      ) : (
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
