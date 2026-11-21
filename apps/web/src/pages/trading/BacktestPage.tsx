import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import {
  toDate,
  toNumber,
  useBacktestStore,
  type BacktestConfig,
} from '@llamatrade/core/stores/backtest';
import { Play, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import {
  RunFailure,
  RunPanel,
  RunSections,
  RunSentence,
  useRunView,
} from '../../components/backtest';
import { HistoryTable } from '../../components/backtest/HistoryTable';
import { Panel } from '../../components/backtest/parts';
import { isFinished } from '../../components/backtest/runData';
import { SetupRanges } from '../../components/backtest/SetupRanges';
import { SkeletonRows } from '../../components/ui/Skeleton';
import { asFrequency } from '../../lib/backtestView';
import { formatNumber } from '../../lib/format';

const isoDay = (ts: Parameters<typeof toDate>[0]) => toDate(ts)?.toISOString().slice(0, 10) ?? '';

/** A stored run's settings, so "Run again" starts from them. */
function configFromRun(run: BacktestRun): Partial<BacktestConfig> {
  const cfg = run.config;
  if (!cfg) return { strategyId: run.strategyId, strategyVersion: run.strategyVersion };
  return {
    strategyId: cfg.strategyId || run.strategyId,
    strategyVersion: cfg.strategyVersion || run.strategyVersion,
    startDate: isoDay(cfg.startDate),
    endDate: isoDay(cfg.endDate),
    initialCapital: toNumber(cfg.initialCapital),
    ...(cfg.commission ? { commission: toNumber(cfg.commission) } : {}),
    ...(cfg.slippagePercent ? { slippage: toNumber(cfg.slippagePercent) } : {}),
    ...(cfg.benchmarkSymbol ? { benchmarkSymbol: cfg.benchmarkSymbol } : {}),
  };
}

/** /backtest: the setup sentence, and the run filling in place below it. */
export default function BacktestPage() {
  const [params, setParams] = useSearchParams();
  const runId = params.get('run');
  const strategyParam = params.get('strategy');
  const rerunId = params.get('rerun');

  const config = useBacktestStore((s) => s.config);
  const setConfig = useBacktestStore((s) => s.setConfig);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const run = useBacktestStore((s) => s.currentBacktest);
  const submitting = useBacktestStore((s) => s.loading);
  const error = useBacktestStore((s) => s.error);
  const history = useBacktestStore((s) => s.history);
  const loadHistory = useBacktestStore((s) => s.loadHistory);
  const runBacktest = useBacktestStore((s) => s.runBacktest);
  const cancelBacktest = useBacktestStore((s) => s.cancelBacktest);
  const getBacktest = useBacktestStore((s) => s.getBacktest);
  const streamProgress = useBacktestStore((s) => s.streamProgress);
  const stopStreaming = useBacktestStore((s) => s.stopStreaming);
  const streaming = useBacktestStore((s) => s.streaming);
  const clearRun = useBacktestStore((s) => s.clearRun);
  const clearError = useBacktestStore((s) => s.clearError);
  const fetchVersionDsl = useBacktestStore((s) => s.fetchVersionDsl);

  const shown = run && run.id === runId ? run : null;
  const view = useRunView(shown);
  const attached = useRef<string | null>(null);
  const dslFor = useRef<string | null>(null);
  const [dsl, setDsl] = useState<string | null | undefined>(undefined);
  const [listFetched, setListFetched] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchStrategies()
      .catch(() => undefined)
      .finally(() => setListFetched(true));
    loadHistory(1, 50).catch(() => undefined);
    return () => stopStreaming();
  }, [fetchStrategies, loadHistory, stopStreaming]);

  // ?strategy= picks the strategy once this visit's fetch of the list has finished.
  useEffect(() => {
    if (!strategyParam || !listFetched) return;
    const s = strategies.find((x) => x.id === strategyParam);
    if (s) setConfig({ strategyId: s.id, strategyVersion: s.version });
    const next = new URLSearchParams(params);
    next.delete('strategy');
    setParams(next, { replace: true });
  }, [strategyParam, strategies, listFetched, setConfig, params, setParams]);

  // ?rerun= copies a stored run's settings into the sentence.
  useEffect(() => {
    if (!rerunId) return;
    const stored = history.runs.find((r) => r.id === rerunId) ?? (run?.id === rerunId ? run : null);
    if (stored) {
      setConfig(configFromRun(stored));
      const next = new URLSearchParams(params);
      next.delete('rerun');
      setParams(next, { replace: true });
    } else {
      getBacktest(rerunId).catch(() => undefined);
    }
  }, [rerunId, history.runs, run, setConfig, getBacktest, params, setParams]);

  // ?run= reattaches to a run after a reload or a return visit.
  useEffect(() => {
    if (!runId) {
      attached.current = null;
      return;
    }
    if (attached.current === runId) return;
    attached.current = runId;
    if (run?.id === runId && (streaming || isFinished(run.status))) return;
    getBacktest(runId)
      .then(() => {
        const loaded = useBacktestStore.getState().currentBacktest;
        if (loaded?.id === runId && !isFinished(loaded.status)) {
          streamProgress(runId).catch(() => undefined);
        }
      })
      .catch(() => undefined);
  }, [runId, run, streaming, getBacktest, streamProgress]);

  // The indicator grid needs the source of the version that ran.
  useEffect(() => {
    if (!shown || shown.status !== BacktestStatus.COMPLETED || dslFor.current === shown.id) return;
    dslFor.current = shown.id;
    setDsl(undefined);
    fetchVersionDsl(shown.strategyId, shown.strategyVersion)
      .then(setDsl)
      .catch(() => setDsl(null));
  }, [shown, fetchVersionDsl, setDsl]);

  const onRun = async () => {
    clearError();
    const id = await runBacktest();
    if (id) {
      attached.current = id;
      setParams({ run: id }, { replace: true });
    }
  };

  const onBack = () => {
    clearRun();
    setParams({}, { replace: true });
  };

  const phase = shown ? view.phase : submitting ? 'pending' : null;
  const active = phase === 'pending' || phase === 'running';
  const selected = strategies.find((s) => s.id === config.strategyId);
  const freq = asFrequency(selected?.rebalance);
  const savedAt = toDate(selected?.updatedAt);
  const versionLine = selected
    ? `v${selected.version}${savedAt ? `, saved ${savedAt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}` : ''}`
    : undefined;

  const sentenceEnd = active ? (
    <>
      <span className="num text-[12px] text-fg-3">
        {phase === 'pending' ? 'Queued' : `Running · ${formatNumber(view.progress, { dp: 0 })}%`}
      </span>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={!shown}
        onClick={() => shown && cancelBacktest(shown.id)}
      >
        <Square className="h-3.5 w-3.5" aria-hidden="true" />
        Cancel
      </button>
    </>
  ) : (
    <>
      {shown && view.phase === 'completed' && (
        <Link to={`/backtest/${shown.id}`} className="btn btn-ghost">
          Open results
        </Link>
      )}
      <button
        type="button"
        className="btn btn-primary"
        disabled={!config.strategyId}
        onClick={onRun}
      >
        <Play className="h-3.5 w-3.5" aria-hidden="true" />
        {shown ? 'Run again' : 'Run backtest'}
      </button>
    </>
  );

  return (
    <div className="page relative isolate grid gap-3.5">
      <h1 className="sr-only">Backtest</h1>
      <Panel>
        <div className="px-4 py-3.5">
          <RunSentence
            config={config}
            strategies={strategies}
            onChange={setConfig}
            locked={active}
            end={sentenceEnd}
          />
          {error && (
            <p role="alert" className="m-0 mt-2.5 text-[12.5px] text-risk">
              {error}
            </p>
          )}
        </div>
      </Panel>

      {phase === null ? (
        <>
          <SetupRanges
            strategyName={selected?.name ?? null}
            strategyId={config.strategyId}
            versionLine={versionLine}
            config={config}
            onChange={setConfig}
            rebalance={freq}
            runs={history.runs}
            metrics={history.metrics}
          />
          {!selected && (
            <Panel
              title="Recent runs"
              aside={
                <Link to="/backtests" className="text-accent hover:underline">
                  All {history.total || ''}
                </Link>
              }
            >
              {history.loading && !history.loaded ? (
                <SkeletonRows rows={3} cols={4} />
              ) : history.runs.length === 0 ? (
                <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
                  No runs yet. Your first one will appear here.
                </p>
              ) : (
                <HistoryTable
                  compact
                  runs={history.runs.slice(0, 3)}
                  metrics={history.metrics}
                  strategies={strategies}
                />
              )}
            </Panel>
          )}
        </>
      ) : (
        <>
          <RunPanel
            run={shown}
            phase={phase}
            log={view.log}
            partial={view.partial}
            progress={view.progress}
            currentDate={view.currentDate}
            strategyName={shown ? view.strategyName : (selected?.name ?? 'Strategy')}
            rebalance={shown ? view.rebalance : freq}
            failure={
              shown && (view.phase === 'failed' || view.phase === 'cancelled') ? (
                <RunFailure
                  phase={view.phase}
                  message={shown.statusMessage}
                  strategyId={shown.strategyId}
                  onBack={onBack}
                />
              ) : undefined
            }
          />
          {shown && view.phase === 'completed' ? (
            <RunSections
              run={shown}
              dsl={dsl}
              onOpenTrades={() => navigate(`/backtest/${shown.id}#trades`)}
            />
          ) : (
            <p className="m-0 text-center text-xs text-fg-3">
              Monthly returns, trades and the indicator grid appear below when the run completes.
            </p>
          )}
        </>
      )}
    </div>
  );
}
