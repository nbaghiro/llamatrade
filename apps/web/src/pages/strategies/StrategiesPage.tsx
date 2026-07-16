import { AlertTriangle, ArrowDown, ArrowUp, Plus, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { MiniChart } from '../../components/strategies/MiniChart';
import { StrategyDetailDrawer } from '../../components/strategies/StrategyDetailDrawer';
import {
  buildRow,
  formatMoneyFull,
  formatReturn,
  STRATEGY_COLORS,
  type StrategyRowView,
} from '../../components/strategies/strategyRow';
import { StrategyTable } from '../../components/strategies/StrategyTable';
import { StrategyTreePreview } from '../../components/strategies/StrategyTreePreview';
import type { BacktestRun } from '../../generated/proto/backtest_pb';
import { StrategyStatus } from '../../generated/proto/strategy_pb';
import { toDate, toNumber, useBacktestStore } from '../../store/backtest';
import { type SortColumn, useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useUIStore } from '../../store/ui';

const STATUS_SEGMENTS: { label: string; value: string }[] = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Paused', value: 'paused' },
  { label: 'Draft', value: 'draft' },
];

function sortValue(row: StrategyRowView, column: SortColumn): number | null {
  switch (column) {
    case 'return':
      return row.returnPct;
    case 'sharpe':
      return row.sharpe;
    case 'allocation':
      return row.allocation;
    case 'updated':
      return row.strategy.updatedAt?.seconds ? Number(row.strategy.updatedAt.seconds) : null;
  }
}

function backtestPeriodYears(run: BacktestRun): number | null {
  const start = toDate(run.config?.startDate);
  const end = toDate(run.config?.endDate);
  if (!start || !end) return null;
  return Math.max(1, Math.round((end.getTime() - start.getTime()) / (365 * 24 * 3600 * 1000)));
}

export default function StrategiesPage() {
  const {
    strategies,
    details,
    detailLoading,
    deployments,
    loading,
    error,
    statusFilter,
    searchQuery,
    sortColumn,
    sortDirection,
    setStatusFilter,
    setSearchQuery,
    setSort,
    fetchStrategies,
    fetchStrategyDetail,
    fetchDeployments,
    deleteStrategy,
    activateStrategy,
    pauseStrategy,
    clearError,
  } = useStrategiesStore();

  const openNewStrategyDialog = useUIStore((state) => state.openNewStrategyDialog);

  const recentRuns = useBacktestStore((state) => state.recentRuns);
  const fetchRecentRuns = useBacktestStore((state) => state.fetchRecentRuns);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerClosed, setDrawerClosed] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    fetchStrategies();
    fetchDeployments();
    fetchRecentRuns();
  }, [fetchStrategies, fetchDeployments, fetchRecentRuns]);

  const strategyNameById = useMemo(() => {
    const map = new Map<string, string>();
    strategies.forEach((s) => map.set(s.id, s.name));
    return map;
  }, [strategies]);

  // Latest completed run per strategy (recentRuns is newest-first, fully hydrated).
  const latestRunByStrategyId = useMemo(() => {
    const map = new Map<string, BacktestRun>();
    recentRuns.forEach((run) => {
      if (!map.has(run.strategyId)) map.set(run.strategyId, run);
    });
    return map;
  }, [recentRuns]);

  // Deployed strategies use the backend series color (shared with the dashboard and
  // portfolio); undeployed strategies fall back to a stable per-slot color.
  const rows = useMemo(
    () =>
      strategies.map((strategy, i) =>
        buildRow(
          strategy,
          latestRunByStrategyId.get(strategy.id) ?? null,
          deployments[strategy.id],
          deployments[strategy.id]?.color || STRATEGY_COLORS[i % STRATEGY_COLORS.length]
        )
      ),
    [strategies, latestRunByStrategyId, deployments]
  );

  const visibleRows = useMemo(() => {
    const dir = sortDirection === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = sortValue(a, sortColumn);
      const bv = sortValue(b, sortColumn);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return (av - bv) * dir;
    });
  }, [rows, sortColumn, sortDirection]);

  useEffect(() => {
    if (visibleRows.length === 0) {
      setSelectedId(null);
      return;
    }
    // Keep a default selection unless the user explicitly closed the drawer.
    const stillValid = selectedId && visibleRows.some((r) => r.strategy.id === selectedId);
    if (!stillValid && !drawerClosed) {
      setSelectedId(visibleRows[0].strategy.id);
    }
  }, [visibleRows, selectedId, drawerClosed]);

  const selectRow = (id: string) => {
    setDrawerClosed(false);
    setSelectedId(id);
  };

  // Hydrate the open strategy's DSL/symbols/timeframe on demand (the list ships
  // summaries only). Cached in the store, so reselecting is instant.
  useEffect(() => {
    if (selectedId && !drawerClosed) fetchStrategyDetail(selectedId);
  }, [selectedId, drawerClosed, fetchStrategyDetail]);

  // Rebuild the selected row from cached detail (real DSL + tags); status stays from the summary, which activate/pause mutate.
  const selectedRow = useMemo(() => {
    if (drawerClosed || !selectedId) return null;
    const base = visibleRows.find((r) => r.strategy.id === selectedId) ?? null;
    if (!base) return null;
    const detail = details[selectedId];
    if (!detail) return base;
    return buildRow(
      { ...detail, status: base.strategy.status },
      base.run,
      deployments[selectedId],
      base.color
    );
  }, [drawerClosed, selectedId, visibleRows, details, deployments]);

  const totalAllocated = useMemo(() => rows.reduce((sum, r) => sum + (r.allocation ?? 0), 0), [rows]);
  const activeCount = strategies.filter((s) => s.status === StrategyStatus.ACTIVE).length;
  const pausedCount = strategies.filter((s) => s.status === StrategyStatus.PAUSED).length;
  const draftCount = strategies.filter((s) => s.status === StrategyStatus.DRAFT).length;

  const recentCells = useMemo(
    () =>
      recentRuns.slice(0, 4).map((run) => {
        const metrics = run.results?.metrics;
        const years = backtestPeriodYears(run);
        const equityCurve = (run.results?.equityCurve ?? []).map((p) => toNumber(p.equity));
        const benchmarkCurve = (run.results?.benchmarkEquityCurve ?? []).map((p) => toNumber(p.equity));
        const hasBenchmark = benchmarkCurve.length > 1;
        const returnPct = metrics ? toNumber(metrics.totalReturn) * 100 : 0;
        return {
          id: run.id,
          name: strategyNameById.get(run.strategyId) ?? 'Strategy',
          date: (toDate(run.completedAt) ?? toDate(run.createdAt) ?? new Date()).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          }),
          period: years ? `${years}y` : '—',
          returnPct,
          sharpe: metrics ? toNumber(metrics.sharpeRatio) : 0,
          equityCurve,
          benchmarkCurve,
          // Excess return over the benchmark ("beat SPY by X%"); null when no benchmark was run.
          alphaPct: hasBenchmark && metrics ? returnPct - toNumber(metrics.benchmarkReturn) * 100 : null,
          benchmarkSymbol: run.results?.benchmarkSymbol || run.config?.benchmarkSymbol || 'SPY',
        };
      }),
    [recentRuns, strategyNameById]
  );

  const runAction = async (fn: () => Promise<unknown>) => {
    setActionLoading(true);
    try {
      await fn();
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = (id: string) => {
    if (!window.confirm('Delete this strategy? This action cannot be undone.')) return;
    void runAction(() => deleteStrategy(id));
  };

  const hasFilters = searchQuery !== '' || statusFilter !== 'all';
  const showEmpty = !loading && visibleRows.length === 0;

  return (
    <div className="min-h-[calc(100vh-56px)] bg-bone bg-grid">
      <div className="max-w-[1760px] mx-auto px-6 lg:px-8 py-6">
        {/* Page header */}
        <div className="flex items-end justify-between mb-4 gap-4 flex-wrap">
          <div>
            <h1 className="font-display uppercase text-4xl leading-none tracking-tight flex items-baseline gap-3">
              Strategies
              <span className="font-mono text-base font-bold text-orange-500 border-2 border-ink px-2 py-0.5 tabular-nums -translate-y-1.5">
                {strategies.length}
              </span>
            </h1>
            <div className="font-mono text-xs text-ink/55 mt-2">
              Sorted by {sortColumn} · {activeCount} active · {pausedCount} paused · {draftCount} drafts
              {'  ·  '}
              {formatMoneyFull(totalAllocated)} deployed
            </div>
          </div>
          <button
            onClick={openNewStrategyDialog}
            className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wide border-2 border-ink px-4 py-3 bg-orange-500 text-ink shadow-[4px_4px_0_rgb(var(--lt-ink))] hover:-translate-x-0.5 hover:-translate-y-0.5 transition-transform"
          >
            <Plus className="w-4 h-4" />
            New Strategy
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-stretch gap-2.5 mb-4 flex-wrap">
          <div className="flex-1 min-w-[240px] flex items-center gap-2.5 border-2 border-ink bg-paper px-3.5 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
            <Search className="w-4 h-4 text-ink/50 flex-none" />
            <input
              type="text"
              placeholder="Search strategies, assets, methods…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-transparent outline-none border-0 focus-visible:ring-0 focus-visible:ring-offset-0 font-mono text-[13px] py-3 text-ink placeholder:text-ink/40"
            />
          </div>

          <div className="flex items-center border-2 border-ink bg-paper shadow-[4px_4px_0_rgb(var(--lt-ink))]">
            <span className="font-mono text-[9px] font-bold uppercase tracking-widest text-ink/45 pl-3 pr-1.5 border-r border-ink/15">
              Status
            </span>
            <div className="flex">
              {STATUS_SEGMENTS.map((seg, i) => (
                <button
                  key={seg.value}
                  onClick={() => setStatusFilter(seg.value)}
                  className={`font-mono text-[11px] font-bold uppercase tracking-wide px-3 py-3 transition-colors ${
                    i > 0 ? 'border-l border-ink/15' : ''
                  } ${statusFilter === seg.value ? 'bg-ink text-bone' : 'text-ink/60 hover:text-ink'}`}
                >
                  {seg.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-50 border-2 border-ink flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-none" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
            <div className="flex items-center gap-2">
              {error.includes('log in') ? (
                <Link to="/login" className="btn btn-secondary btn-sm">
                  Log In
                </Link>
              ) : (
                <button onClick={() => fetchStrategies()} className="btn btn-secondary btn-sm">
                  <RefreshCw className="w-4 h-4" />
                  Retry
                </button>
              )}
              <button onClick={clearError} className="btn btn-ghost btn-sm">
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Split: table + drawer */}
        {loading && rows.length === 0 ? (
          <div className="card-shadow py-16 text-center font-mono text-xs uppercase tracking-wide text-ink/50">
            Loading strategies…
          </div>
        ) : strategies.length === 0 && !hasFilters ? (
          <div className="card-shadow">
            <StrategyTreePreview onCreateStrategy={openNewStrategyDialog} onBrowseTemplates={openNewStrategyDialog} />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_388px] gap-4 items-start">
            <div className="flex flex-col gap-4 min-w-0">
              {showEmpty ? (
                <div className="card-shadow py-16 px-8 text-center">
                  <h3 className="font-display uppercase text-2xl leading-tight text-ink">
                    Nothing matches those filters
                  </h3>
                  <p className="font-mono text-xs text-ink/55 mt-2">Clear a filter to widen the list.</p>
                </div>
              ) : (
                <StrategyTable
                  rows={visibleRows}
                  totalCount={strategies.length}
                  totalAllocated={totalAllocated}
                  selectedId={selectedRow ? selectedId : null}
                  onSelect={selectRow}
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onSort={setSort}
                />
              )}

              {/* Recent backtests strip */}
              {recentCells.length > 0 && (
                <div className="card-shadow">
                  <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
                    <span className="font-mono text-[11px] font-bold uppercase tracking-widest text-ink">
                      Recent Backtests
                    </span>
                    <Link
                      to="/backtest"
                      className="font-mono text-[10.5px] font-bold uppercase tracking-wide text-orange-500 hover:text-orange-600"
                    >
                      All runs →
                    </Link>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4">
                    {recentCells.map((cell, i) => {
                      const positive = cell.returnPct >= 0;
                      return (
                        <div
                          key={cell.id}
                          className={`flex flex-col px-3.5 py-3.5 ${
                            i > 0 ? 'border-l border-ink/10' : ''
                          } ${i >= 2 ? 'border-t border-ink/10 sm:border-t-0' : ''}`}
                        >
                          <div className="font-bold text-[13px] leading-tight truncate text-ink">
                            {cell.name}
                          </div>

                          {/* Equity sparkline — echoes the detail panel's chart */}
                          <div className="mt-2.5">
                            {cell.equityCurve.length > 1 ? (
                              <MiniChart
                                data={cell.equityCurve}
                                positive={positive}
                                showBenchmark={false}
                                height={38}
                                fluid
                              />
                            ) : (
                              <div className="h-[38px] flex items-center font-mono text-[9px] uppercase tracking-wide text-ink/30">
                                No curve
                              </div>
                            )}
                          </div>

                          {/* Return + risk-adjusted */}
                          <div className="flex items-baseline gap-2 mt-2.5">
                            <span
                              className={`font-mono font-bold text-[17px] leading-none tabular-nums ${
                                positive ? 'text-green-500' : 'text-red-500'
                              }`}
                            >
                              {formatReturn(cell.returnPct)}
                            </span>
                            <span className="font-mono text-[9.5px] text-ink/45 tabular-nums">
                              {cell.sharpe.toFixed(2)} SR
                            </span>
                          </div>

                          {/* Excess return vs benchmark — the "did it beat SPY?" signal */}
                          <div className="mt-1.5 flex items-center gap-1 font-mono text-[9.5px] uppercase tracking-wide tabular-nums">
                            {cell.alphaPct === null ? (
                              <span className="text-ink/35">No benchmark</span>
                            ) : (
                              <>
                                <span className="text-ink/45">vs {cell.benchmarkSymbol}</span>
                                <span
                                  className={`inline-flex items-center gap-0.5 font-bold ${
                                    cell.alphaPct >= 0 ? 'text-green-500' : 'text-red-500'
                                  }`}
                                >
                                  {cell.alphaPct >= 0 ? (
                                    <ArrowUp className="w-2.5 h-2.5" />
                                  ) : (
                                    <ArrowDown className="w-2.5 h-2.5" />
                                  )}
                                  {formatReturn(cell.alphaPct)}
                                </span>
                              </>
                            )}
                          </div>

                          <div className="mt-1.5 font-mono text-[9px] uppercase tracking-wide text-ink/40">
                            {cell.date} · {cell.period}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Drawer */}
            {selectedRow && (
              <StrategyDetailDrawer
                row={selectedRow}
                dslLoading={selectedId ? !!detailLoading[selectedId] : false}
                onClose={() => setDrawerClosed(true)}
                onActivate={(id) => void runAction(() => activateStrategy(id))}
                onPause={(id) => void runAction(() => pauseStrategy(id))}
                onDelete={handleDelete}
                actionLoading={actionLoading}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
