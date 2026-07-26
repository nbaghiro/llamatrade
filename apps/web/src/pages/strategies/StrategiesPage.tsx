import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { type SortColumn, useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { AlertTriangle, Plus, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

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

interface KpiTileProps {
  label: string;
  value: string;
  dark?: boolean;
  accent?: 'green';
}

function KpiTile({ label, value, dark, accent }: KpiTileProps) {
  return (
    <div className={`min-w-[110px] flex-1 border-2 border-ink px-4 py-2.5 ${dark ? 'bg-ink' : 'bg-paper'}`}>
      <div className={`font-mono text-[9px] font-bold uppercase tracking-[0.1em] ${dark ? 'text-bone/55' : 'text-ink/50'}`}>
        {label}
      </div>
      <div
        className={`mt-1.5 font-mono text-[19px] font-bold leading-none tabular-nums ${
          dark ? 'text-orange-500' : accent === 'green' ? 'text-green-500' : 'text-ink'
        }`}
      >
        {value}
      </div>
    </div>
  );
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
  const draftCount = strategies.filter((s) => s.status === StrategyStatus.DRAFT).length;

  const bestReturn = useMemo(
    () =>
      rows.reduce<number | null>(
        (best, r) => (r.returnPct !== null && (best === null || r.returnPct > best) ? r.returnPct : best),
        null
      ),
    [rows]
  );
  const avgSharpe = useMemo(() => {
    const vals = rows.map((r) => r.sharpe).filter((s): s is number => s !== null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  }, [rows]);

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
      <div className="mx-auto max-w-[1760px] px-6 py-6 lg:px-8">
        {/* Page header */}
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <h1 className="flex items-baseline gap-3 font-display text-4xl uppercase leading-none tracking-tight">
            Strategies
            <span className="-translate-y-1.5 border-2 border-ink px-2 py-0.5 font-mono text-base font-bold tabular-nums text-orange-500">
              {strategies.length}
            </span>
          </h1>
          <button
            onClick={openNewStrategyDialog}
            className="flex items-center gap-2 border-2 border-ink bg-orange-500 px-4 py-3 font-mono text-xs font-bold uppercase tracking-wide text-ink shadow-[4px_4px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5"
          >
            <Plus className="h-4 w-4" />
            New Strategy
          </button>
        </div>

        {/* KPI strip */}
        <div className="mb-4 flex flex-wrap gap-2.5">
          <KpiTile label="Deployed" value={formatMoneyFull(totalAllocated)} dark />
          <KpiTile label="Live · Paper" value={String(activeCount)} />
          <KpiTile label="Drafts" value={String(draftCount)} />
          <KpiTile
            label="Best Return"
            value={bestReturn !== null ? formatReturn(bestReturn) : '—'}
            accent={bestReturn !== null && bestReturn >= 0 ? 'green' : undefined}
          />
          <KpiTile label="Avg Sharpe" value={avgSharpe !== null ? avgSharpe.toFixed(2) : '—'} />
        </div>

        {/* Toolbar */}
        <div className="mb-4 flex flex-wrap items-stretch gap-2.5">
          <div className="flex min-w-[240px] flex-1 items-center gap-2.5 border-2 border-ink bg-paper px-3.5 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
            <Search className="h-4 w-4 flex-none text-ink/50" />
            <input
              type="text"
              placeholder="Search strategies, assets, methods…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full border-0 bg-transparent py-3 font-mono text-[13px] text-ink outline-none placeholder:text-ink/40 focus-visible:ring-0 focus-visible:ring-offset-0"
            />
          </div>

          <div className="flex items-center border-2 border-ink bg-paper shadow-[4px_4px_0_rgb(var(--lt-ink))]">
            <span className="border-r border-ink/15 pl-3 pr-1.5 font-mono text-[9px] font-bold uppercase tracking-widest text-ink/45">
              Status
            </span>
            <div className="flex">
              {STATUS_SEGMENTS.map((seg, i) => (
                <button
                  key={seg.value}
                  onClick={() => setStatusFilter(seg.value)}
                  className={`px-3 py-3 font-mono text-[11px] font-bold uppercase tracking-wide transition-colors ${
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
          <div className="mb-4 flex items-center justify-between gap-3 border-2 border-ink bg-red-50 p-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 flex-none text-red-600" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
            <div className="flex items-center gap-2">
              {error.includes('log in') ? (
                <Link to="/login" className="btn btn-secondary btn-sm">
                  Log In
                </Link>
              ) : (
                <button onClick={() => fetchStrategies()} className="btn btn-secondary btn-sm">
                  <RefreshCw className="h-4 w-4" />
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
          <div
            className={`grid grid-cols-1 items-start gap-4 ${
              selectedRow ? 'lg:grid-cols-[3fr_2fr]' : ''
            }`}
          >
            <div className="min-w-0">
              {showEmpty ? (
                <div className="card-shadow px-8 py-16 text-center">
                  <h3 className="font-display text-2xl uppercase leading-tight text-ink">
                    Nothing matches those filters
                  </h3>
                  <p className="mt-2 font-mono text-xs text-ink/55">Clear a filter to widen the list.</p>
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
