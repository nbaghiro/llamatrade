import {
  AlertTriangle,
  ChevronDown,
  Clock,
  Loader2,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { generateChartData, generateBenchmarkData } from '../../data/demo-strategies';
import { StrategyStatus } from '../../generated/proto/strategy_pb';
import { useStrategiesStore } from '../../store/strategies';

function MiniChart({
  data,
  benchmarkData,
  positive,
}: {
  data: number[];
  benchmarkData: number[];
  positive: boolean;
}) {
  // Calculate combined min/max for both lines to share the same scale
  const allValues = [...data, ...benchmarkData];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * 140;
        const y = 40 - ((v - min) / range) * 34;
        return `${x},${y}`;
      })
      .join(' ');

  const strategyPoints = toPoints(data);
  const benchmarkPoints = toPoints(benchmarkData);
  const fillPoints = `0,40 ${strategyPoints} 140,40`;
  const gradientId = `gradient-${positive ? 'pos' : 'neg'}-${Math.random().toString(36).slice(2)}`;

  return (
    <svg width="140" height="44" className="overflow-visible">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0.15" />
          <stop offset="100%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Strategy fill area */}
      <polygon points={fillPoints} fill={`url(#${gradientId})`} />
      {/* Benchmark line (SPY) - dashed gray */}
      <polyline
        points={benchmarkPoints}
        fill="none"
        stroke="#9ca3af"
        strokeWidth="1.5"
        strokeDasharray="3,2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="dark:stroke-gray-500"
      />
      {/* Strategy line */}
      <polyline
        points={strategyPoints}
        fill="none"
        stroke={positive ? '#22c55e' : '#ef4444'}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function StatusBadge({ status }: { status: StrategyStatus }) {
  const styleMap: Record<StrategyStatus, string> = {
    [StrategyStatus.ACTIVE]: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
    [StrategyStatus.DRAFT]: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    [StrategyStatus.PAUSED]: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400',
    [StrategyStatus.ARCHIVED]: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
    [StrategyStatus.UNSPECIFIED]: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
  };

  const labelMap: Record<StrategyStatus, string> = {
    [StrategyStatus.ACTIVE]: 'Active',
    [StrategyStatus.DRAFT]: 'Draft',
    [StrategyStatus.PAUSED]: 'Paused',
    [StrategyStatus.ARCHIVED]: 'Archived',
    [StrategyStatus.UNSPECIFIED]: 'Unknown',
  };

  return (
    <span
      className={`px-2 py-0.5 text-xs font-medium rounded-full ${styleMap[status] || styleMap[StrategyStatus.DRAFT]}`}
    >
      {labelMap[status] || 'Unknown'}
    </span>
  );
}

// Derive implementation type from strategy fields (templateId, dslCode)
type ImplementationType = 'dsl' | 'template' | 'custom';

function getImplementationType(strategy: { templateId?: string; dslCode?: string }): ImplementationType {
  if (strategy.templateId) return 'template';
  if (strategy.dslCode) return 'dsl';
  return 'custom';
}

function TypeBadge({ type }: { type: ImplementationType }) {
  const labels: Record<ImplementationType, string> = {
    dsl: 'DSL',
    template: 'Template',
    custom: 'Custom',
  };

  return (
    <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
      {labels[type]}
    </span>
  );
}

// Convert proto Timestamp to human-readable time ago
function formatTimeAgo(timestamp: { seconds: bigint; nanos: number } | undefined): string {
  if (!timestamp) return 'Unknown';

  const date = new Date(Number(timestamp.seconds) * 1000);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  return 'Just now';
}

// Generate a hash code from string for deterministic chart data
function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

export default function StrategiesPage() {
  // Store state and actions
  const {
    strategies,
    loading,
    error,
    fetchStrategies,
    deleteStrategy,
    activateStrategy,
    pauseStrategy,
    statusFilter,
    typeFilter,
    searchQuery,
    setStatusFilter,
    setTypeFilter,
    setSearchQuery,
    clearError,
  } = useStrategiesStore();

  // Local UI state
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Fetch strategies on mount
  useEffect(() => {
    fetchStrategies();
  }, [fetchStrategies]);

  // Generate chart data for each strategy (deterministic based on ID)
  const strategiesWithCharts = useMemo(() => {
    return strategies.map((strategy) => {
      const seed = hashCode(strategy.id);
      // Use bestReturn if available, otherwise default to 0
      const returnValue = strategy.bestReturn?.value ? parseFloat(strategy.bestReturn.value) : 0;
      return {
        ...strategy,
        chartData: generateChartData(returnValue, seed * 31 + 7),
        benchmarkData: generateBenchmarkData(seed * 17 + 42),
        returnValue,
        sharpeValue: strategy.bestSharpe?.value ? parseFloat(strategy.bestSharpe.value) : 0,
      };
    });
  }, [strategies]);

  // Action handlers
  const handleDelete = useCallback(async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this strategy? This action cannot be undone.')) {
      return;
    }
    setDeletingId(id);
    setActionLoading(true);
    try {
      await deleteStrategy(id);
    } finally {
      setDeletingId(null);
      setActionLoading(false);
      setOpenMenuId(null);
    }
  }, [deleteStrategy]);

  const handleActivate = useCallback(async (id: string) => {
    setActionLoading(true);
    try {
      await activateStrategy(id);
    } finally {
      setActionLoading(false);
      setOpenMenuId(null);
    }
  }, [activateStrategy]);

  const handlePause = useCallback(async (id: string) => {
    setActionLoading(true);
    try {
      await pauseStrategy(id);
    } finally {
      setActionLoading(false);
      setOpenMenuId(null);
    }
  }, [pauseStrategy]);

  return (
    <div className="min-h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950 bg-dotted-grid">
      <div className="px-12 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Strategies</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {loading ? 'Loading...' : `${strategiesWithCharts.length} ${strategiesWithCharts.length === 1 ? 'strategy' : 'strategies'}`}
            </p>
          </div>
          <Link
            to="/strategies/new"
            className="flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            New Strategy
          </Link>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
            <div className="flex items-center gap-2">
              {error.includes('log in') ? (
                <Link
                  to="/login"
                  className="px-3 py-1.5 text-sm text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
                >
                  Log In
                </Link>
              ) : (
                <button
                  onClick={() => fetchStrategies()}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  Retry
                </button>
              )}
              <button
                onClick={clearError}
                className="px-3 py-1.5 text-sm text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative flex-1 min-w-[200px] max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search strategies..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>

          <div className="relative">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="appearance-none pl-3 pr-8 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none cursor-pointer"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="draft">Draft</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>

          <div className="relative">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="appearance-none pl-3 pr-8 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none cursor-pointer"
            >
              <option value="all">All Types</option>
              <option value="dsl">DSL</option>
              <option value="python">Python</option>
              <option value="template">Template</option>
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>

        {/* Strategy List */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          {loading && strategiesWithCharts.length === 0 ? (
            // Loading state
            <div className="py-16 text-center">
              <Loader2 className="w-8 h-8 text-primary-500 animate-spin mx-auto mb-4" />
              <p className="text-gray-500 dark:text-gray-400">Loading strategies...</p>
            </div>
          ) : strategiesWithCharts.length === 0 ? (
            // Empty state
            <div className="py-16 text-center">
              <div className="w-12 h-12 bg-gray-100 dark:bg-gray-800 rounded-xl flex items-center justify-center mx-auto mb-4">
                <Search className="w-6 h-6 text-gray-400" />
              </div>
              <p className="text-gray-500 dark:text-gray-400 mb-1">No strategies found</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mb-4">
                {searchQuery || statusFilter !== 'all' || typeFilter !== 'all'
                  ? 'Try adjusting your search or filters'
                  : 'Create your first strategy to get started'}
              </p>
              {!searchQuery && statusFilter === 'all' && typeFilter === 'all' && (
                <Link
                  to="/strategies/new"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Create Strategy
                </Link>
              )}
            </div>
          ) : (
            // Strategy list
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {strategiesWithCharts.map((strategy) => (
                <div
                  key={strategy.id}
                  className={`flex items-center gap-6 px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group ${
                    deletingId === strategy.id ? 'opacity-50' : ''
                  }`}
                >
                  {/* Performance Chart */}
                  <div className="hidden sm:block w-36 flex-shrink-0">
                    <MiniChart
                      data={strategy.chartData}
                      benchmarkData={strategy.benchmarkData}
                      positive={strategy.returnValue >= 0}
                    />
                  </div>

                  {/* Name & Description */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Link
                        to={`/strategies/${strategy.id}`}
                        className="font-medium text-gray-900 dark:text-gray-100 hover:text-primary-600 dark:hover:text-primary-400 truncate"
                      >
                        {strategy.name}
                      </Link>
                      <StatusBadge status={strategy.status} />
                      <TypeBadge type={getImplementationType(strategy)} />
                    </div>
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                      {strategy.description || 'No description'}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-400 dark:text-gray-500">
                      <span>{strategy.symbols.length > 0 ? strategy.symbols.join(', ') : 'No symbols'}</span>
                      <span>•</span>
                      <span>{strategy.timeframe || '1D'}</span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatTimeAgo(strategy.updatedAt)}
                      </span>
                    </div>
                  </div>

                  {/* Performance Stats */}
                  <div className="hidden md:flex items-center gap-6 text-right">
                    <div>
                      <p
                        className={`text-sm font-semibold font-mono ${
                          strategy.returnValue >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                        }`}
                      >
                        {strategy.returnValue >= 0 ? '+' : ''}
                        {strategy.returnValue.toFixed(1)}%
                      </p>
                      <p className="text-xs text-gray-400">Return</p>
                    </div>
                    <div>
                      <p className="text-sm font-semibold font-mono text-gray-900 dark:text-gray-100">
                        {strategy.sharpeValue.toFixed(2)}
                      </p>
                      <p className="text-xs text-gray-400">Sharpe</p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Link
                      to={`/strategies/${strategy.id}`}
                      className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                      title="Edit"
                    >
                      <Pencil className="w-4 h-4" />
                    </Link>
                    <Link
                      to={`/backtest?strategy=${strategy.id}`}
                      className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                      title="Run Backtest"
                    >
                      <Play className="w-4 h-4" />
                    </Link>
                    <div className="relative">
                      <button
                        onClick={() => setOpenMenuId(openMenuId === strategy.id ? null : strategy.id)}
                        className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        disabled={actionLoading}
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                      {openMenuId === strategy.id && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setOpenMenuId(null)} />
                          <div className="absolute right-0 top-full mt-1 w-44 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
                            {/* Activate/Pause based on current status */}
                            {strategy.status === StrategyStatus.ACTIVE ? (
                              <button
                                onClick={() => handlePause(strategy.id)}
                                disabled={actionLoading}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
                              >
                                <Pause className="w-4 h-4" />
                                Pause Strategy
                              </button>
                            ) : (
                              <button
                                onClick={() => handleActivate(strategy.id)}
                                disabled={actionLoading}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
                              >
                                <Play className="w-4 h-4" />
                                Activate Strategy
                              </button>
                            )}
                            <button
                              onClick={() => handleDelete(strategy.id)}
                              disabled={actionLoading}
                              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
                            >
                              <Trash2 className="w-4 h-4" />
                              Delete
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
