/**
 * Strategy Picker Modal
 * Modal for selecting a strategy with mini chart previews.
 */

import { Loader2, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type { Strategy } from '../../generated/proto/strategy_pb';
import { strategyClient } from '../../services/grpc-client';
import { getTenantContext } from '../../store/auth';

interface StrategyPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (strategy: Strategy) => void;
  selectedId?: string;
}

// Generate deterministic chart data from strategy ID
function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash;
  }
  return Math.abs(hash);
}

function generateChartData(returnValue: number, seed: number): number[] {
  const points = 20;
  const data: number[] = [];
  let value = 100;

  for (let i = 0; i < points; i++) {
    const noise = ((seed * (i + 1) * 7) % 100) / 100 - 0.5;
    const trend = (returnValue / points) * (i / points);
    value = value * (1 + trend / 100 + noise * 0.02);
    data.push(value);
  }
  return data;
}

function MiniChart({ data, positive }: { data: number[]; positive: boolean }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 30 - ((v - min) / range) * 24;
      return `${x},${y}`;
    })
    .join(' ');

  const fillPoints = `0,30 ${points} 100,30`;
  const gradientId = `picker-gradient-${Math.random().toString(36).slice(2)}`;

  return (
    <svg width="100" height="32" viewBox="0 0 100 32" className="overflow-visible">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0.2" />
          <stop offset="100%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={fillPoints} fill={`url(#${gradientId})`} />
      <polyline
        points={points}
        fill="none"
        stroke={positive ? '#22c55e' : '#ef4444'}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function StrategyPickerModal({
  isOpen,
  onClose,
  onSelect,
  selectedId,
}: StrategyPickerModalProps) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (!isOpen) return;

    async function fetchStrategies() {
      setLoading(true);
      const context = getTenantContext();
      if (!context) {
        setStrategies([]);
        setLoading(false);
        return;
      }

      try {
        const response = await strategyClient.listStrategies({
          context,
          pagination: { page: 1, pageSize: 50 },
        });
        setStrategies(response.strategies);
      } catch {
        setStrategies([]);
      } finally {
        setLoading(false);
      }
    }

    fetchStrategies();
  }, [isOpen]);

  const strategiesWithCharts = useMemo(() => {
    return strategies.map((strategy) => {
      const seed = hashCode(strategy.id);
      const returnValue = strategy.bestReturn?.value ? parseFloat(strategy.bestReturn.value) : 0;
      return {
        ...strategy,
        chartData: generateChartData(returnValue, seed),
        returnValue,
      };
    });
  }, [strategies]);

  const filteredStrategies = useMemo(() => {
    if (!searchQuery) return strategiesWithCharts;
    const query = searchQuery.toLowerCase();
    return strategiesWithCharts.filter(
      (s) =>
        s.name.toLowerCase().includes(query) ||
        (s.description && s.description.toLowerCase().includes(query))
    );
  }, [strategiesWithCharts, searchQuery]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Select Strategy
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search strategies..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
              autoFocus
            />
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(80vh - 140px)' }}>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
            </div>
          ) : filteredStrategies.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400">
                {strategies.length === 0 ? 'No strategies found' : 'No matching strategies'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {filteredStrategies.map((strategy) => (
                <button
                  key={strategy.id}
                  onClick={() => {
                    onSelect(strategy);
                    onClose();
                  }}
                  className={`w-full flex items-center gap-4 px-6 py-4 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors ${
                    selectedId === strategy.id
                      ? 'bg-primary-50 dark:bg-primary-900/20 border-l-2 border-primary-500'
                      : ''
                  }`}
                >
                  {/* Mini Chart */}
                  <div className="flex-shrink-0 w-24">
                    <MiniChart data={strategy.chartData} positive={strategy.returnValue >= 0} />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">
                      {strategy.name}
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                      {strategy.description || 'No description'}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {strategy.symbols.slice(0, 3).map((symbol) => (
                        <span
                          key={symbol}
                          className="px-1.5 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                        >
                          {symbol}
                        </span>
                      ))}
                      {strategy.symbols.length > 3 && (
                        <span className="text-xs text-gray-400">
                          +{strategy.symbols.length - 3}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Return */}
                  <div className="text-right">
                    <p
                      className={`text-sm font-semibold font-mono ${
                        strategy.returnValue >= 0
                          ? 'text-green-600 dark:text-green-400'
                          : 'text-red-600 dark:text-red-400'
                      }`}
                    >
                      {strategy.returnValue >= 0 ? '+' : ''}
                      {strategy.returnValue.toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-400">Best Return</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
