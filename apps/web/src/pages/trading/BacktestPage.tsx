/**
 * Backtest workspace — config rail + results main (Backtest v1).
 * Wired end-to-end to BacktestService: recent runs, full run results (metrics,
 * equity/benchmark curves, monthly returns) and the paged trade log.
 */

import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber, useBacktestStore, type BacktestConfig } from '@llamatrade/core/stores/backtest';
import { AlertTriangle } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import BacktestConfigForm from '../../components/backtest/BacktestConfigForm';
import BacktestProgress from '../../components/backtest/BacktestProgress';
import DrawdownChart from '../../components/backtest/DrawdownChart';
import EquityCurveChart from '../../components/backtest/EquityCurveChart';
import MetricsPanel from '../../components/backtest/MetricsPanel';
import MonthlyReturnsGrid from '../../components/backtest/MonthlyReturnsGrid';
import RecentRunsPanel from '../../components/backtest/RecentRunsPanel';
import TradesTable from '../../components/backtest/TradesTable';

function isoDate(run: BacktestRun, field: 'startDate' | 'endDate'): string {
  const ts = run.config?.[field];
  const date = toDate(ts);
  return date ? date.toLocaleDateString('en-CA') : '';
}

// Mirror a stored run's config back into the rail so a recalled run is editable.
function configFromRun(run: BacktestRun): Partial<BacktestConfig> {
  const cfg = run.config;
  if (!cfg) return {};
  return {
    strategyId: cfg.strategyId,
    strategyVersion: cfg.strategyVersion,
    startDate: isoDate(run, 'startDate'),
    endDate: isoDate(run, 'endDate'),
    initialCapital: toNumber(cfg.initialCapital),
    commission: toNumber(cfg.commission),
    slippage: toNumber(cfg.slippagePercent),
    timeframe: cfg.timeframe,
    benchmarkSymbol: cfg.benchmarkSymbol,
  };
}

export default function BacktestPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const {
    currentBacktest,
    config,
    setConfig,
    loading,
    progress,
    progressMessage,
    error,
    strategies,
    recentRuns,
    recentRunsLoading,
    fullTrades,
    tradesLoading,
    runBacktest,
    getBacktest,
    cancelBacktest,
    loadAllTrades,
    fetchRecentRuns,
    clearError,
  } = useBacktestStore();

  const urlId = searchParams.get('id');
  const urlStrategy = searchParams.get('strategy') ?? undefined;

  // Hydrate recent runs on mount.
  useEffect(() => {
    fetchRecentRuns();
  }, [fetchRecentRuns]);

  // Load a backtest referenced by the URL.
  useEffect(() => {
    if (urlId && currentBacktest?.id !== urlId) {
      getBacktest(urlId);
    }
  }, [urlId, currentBacktest?.id, getBacktest]);

  // With no ?id=, open the most recent completed run so results render on load.
  useEffect(() => {
    if (!urlId && !currentBacktest && recentRuns.length > 0) {
      const latest = recentRuns.find((r) => r.status === BacktestStatus.COMPLETED) ?? recentRuns[0];
      if (latest) getBacktest(latest.id);
    }
  }, [urlId, currentBacktest, recentRuns, getBacktest]);

  // Seed the rail from a ?strategy= deep link.
  useEffect(() => {
    if (urlStrategy && !config.strategyId) {
      setConfig({ strategyId: urlStrategy });
    }
  }, [urlStrategy, config.strategyId, setConfig]);

  const handleRun = async () => {
    const id = await runBacktest();
    if (id) setSearchParams({ id });
  };

  const handleSelectRun = (id: string) => {
    const run = recentRuns.find((r) => r.id === id);
    if (run) setConfig(configFromRun(run));
    getBacktest(id);
    setSearchParams({ id });
  };

  const isRunning =
    currentBacktest?.status === BacktestStatus.RUNNING ||
    currentBacktest?.status === BacktestStatus.PENDING;
  const isFailed = currentBacktest?.status === BacktestStatus.FAILED;
  const results = currentBacktest?.status === BacktestStatus.COMPLETED ? currentBacktest.results : undefined;

  const strategyName = useMemo(() => {
    const id = currentBacktest?.strategyId || config.strategyId;
    return strategies.find((s) => s.id === id)?.name ?? id ?? 'Strategy';
  }, [strategies, currentBacktest?.strategyId, config.strategyId]);

  const subline = useMemo(() => {
    if (isRunning) return <>Running <b className="text-ink">{strategyName}</b>…</>;
    if (results && currentBacktest) {
      const start = isoDate(currentBacktest, 'startDate');
      const end = isoDate(currentBacktest, 'endDate');
      const days = results.equityCurve.length;
      const startedAt = toDate(currentBacktest.startedAt);
      const completedAt = toDate(currentBacktest.completedAt);
      const secs =
        startedAt && completedAt ? (completedAt.getTime() - startedAt.getTime()) / 1000 : null;
      return (
        <>
          Simulating <b className="text-ink">{strategyName}</b> · {start} → {end} ·{' '}
          <b className="text-ink">{days.toLocaleString()}</b> trading days
          {secs !== null && secs >= 0 ? <> · completed in <b className="text-ink">{secs.toFixed(1)}s</b></> : null}
        </>
      );
    }
    return <>Configure a strategy and run a historical simulation.</>;
  }, [isRunning, results, currentBacktest, strategyName]);

  const lastRunLabel = useMemo(() => {
    if (!results || !currentBacktest) return null;
    const completedAt = toDate(currentBacktest.completedAt);
    const startedAt = toDate(currentBacktest.startedAt);
    if (!completedAt) return null;
    const when = completedAt.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
    const secs = startedAt ? (completedAt.getTime() - startedAt.getTime()) / 1000 : null;
    return `Last run · ${when}${secs !== null && secs >= 0 ? ` · ${secs.toFixed(1)}s` : ''}`;
  }, [results, currentBacktest]);

  const trades = fullTrades ?? results?.trades ?? [];
  const totalTrades = results?.metrics?.totalTrades ?? results?.trades.length ?? 0;
  const benchmarkSymbol =
    results?.benchmarkSymbol || results?.metrics?.benchmarkSymbol || config.benchmarkSymbol;

  return (
    <div className="h-[calc(100vh-56px)] bg-bone bg-grid overflow-y-auto">
      <div className="max-w-[1760px] mx-auto px-6 lg:px-8 py-6 pb-16">
        {/* Header */}
        <div className="flex items-end justify-between gap-3 flex-wrap mb-5">
          <div>
            <h1 className="font-display uppercase text-[42px] leading-[0.9] tracking-[0.01em]">Backtest</h1>
            <div className="mt-2 font-mono text-[12px] text-ink/55">{subline}</div>
          </div>
          <span className="inline-flex items-center gap-2 border-2 border-ink bg-paper px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.08em]">
            <span className="w-2 h-2 bg-orange-500" />
            Paper Simulation
          </span>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-4 flex items-center justify-between gap-3 border-2 border-ink bg-red-50 px-4 py-3">
            <span className="flex items-center gap-2.5">
              <AlertTriangle className="w-4 h-4 text-red-600" />
              <span className="font-mono text-[13px] text-red-700">{error}</span>
            </span>
            <button
              onClick={clearError}
              className="font-mono text-[11px] font-bold uppercase tracking-[0.05em] text-red-700 hover:text-ink"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Layout: config rail + results main */}
        <div className="grid grid-cols-1 lg:grid-cols-[322px_1fr] gap-[18px] items-start">
          {/* Rail */}
          <div className="flex flex-col gap-4 lg:sticky lg:top-[18px]">
            <BacktestConfigForm onRun={handleRun} loading={loading} lastRunLabel={lastRunLabel} />
            <RecentRunsPanel
              runs={recentRuns}
              strategies={strategies}
              selectedId={currentBacktest?.id}
              loading={recentRunsLoading}
              onSelect={handleSelectRun}
            />
          </div>

          {/* Main */}
          <div className="flex flex-col gap-4 min-w-0">
            {isRunning && currentBacktest && (
              <BacktestProgress
                backtest={currentBacktest}
                progress={progress}
                message={progressMessage}
                onCancel={() => cancelBacktest(currentBacktest.id)}
              />
            )}

            {isFailed && currentBacktest && (
              <div className="border-2 border-ink bg-red-50 shadow-[4px_4px_0_#0d0d0d] p-6">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
                  <div>
                    <h3 className="font-display uppercase tracking-tight text-red-700">Backtest Failed</h3>
                    <p className="mt-1 font-mono text-[13px] text-red-700/90">
                      {currentBacktest.statusMessage || 'An error occurred during the backtest.'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {results && currentBacktest && (
              <>
                {results.metrics && <MetricsPanel metrics={results.metrics} />}
                <EquityCurveChart
                  data={results.equityCurve}
                  benchmark={results.benchmarkEquityCurve}
                  benchmarkSymbol={benchmarkSymbol}
                  strategyName={strategyName}
                  metrics={results.metrics}
                />
                <DrawdownChart data={results.equityCurve} metrics={results.metrics} />
                <MonthlyReturnsGrid monthlyReturns={results.monthlyReturns} />
                <TradesTable
                  trades={trades}
                  totalTrades={totalTrades}
                  metrics={results.metrics}
                  onLoadAll={() => loadAllTrades(currentBacktest.id)}
                  loadingAll={tradesLoading}
                />
              </>
            )}

            {!isRunning && !isFailed && !results && (
              <div className="border-2 border-dashed border-ink/30 bg-paper/60 p-12 flex flex-col items-center justify-center text-center gap-2 min-h-[320px]">
                <span className="font-display uppercase text-[28px] tracking-tight text-ink/25">
                  No results yet
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-ink/40">
                  Configure a strategy and run a backtest, or pick a recent run.
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
