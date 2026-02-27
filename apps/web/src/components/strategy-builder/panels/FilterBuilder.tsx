import { X } from 'lucide-react';
import { useState, useCallback } from 'react';

import type {
  FilterConfig,
  FilterSelection,
  FilterUniverse,
  FilterSortBy,
  FilterPeriod,
} from '../../../types/strategy-builder';
import {
  FILTER_UNIVERSES,
  FILTER_SORT_OPTIONS,
  FILTER_PERIODS,
} from '../../../types/strategy-builder';

interface FilterBuilderProps {
  initialConfig?: FilterConfig;
  onSave: (config: FilterConfig) => void;
  onCancel: () => void;
}

export function FilterBuilder({ initialConfig, onSave, onCancel }: FilterBuilderProps) {
  const [selection, setSelection] = useState<FilterSelection>(initialConfig?.selection || 'top');
  const [count, setCount] = useState(initialConfig?.count || 10);
  const [universe, setUniverse] = useState<FilterUniverse>(initialConfig?.universe || 'sp500');
  const [sortBy, setSortBy] = useState<FilterSortBy>(initialConfig?.sortBy || 'momentum');
  const [period, setPeriod] = useState<FilterPeriod>(initialConfig?.period || '12m');
  const [customSymbols, setCustomSymbols] = useState(
    initialConfig?.customSymbols?.join(', ') || ''
  );

  const handleSave = useCallback(() => {
    const config: FilterConfig = {
      selection,
      count,
      universe,
      sortBy,
      period,
      customSymbols:
        universe === 'custom'
          ? customSymbols
              .split(',')
              .map((s) => s.trim().toUpperCase())
              .filter(Boolean)
          : undefined,
    };
    onSave(config);
  }, [selection, count, universe, sortBy, period, customSymbols, onSave]);

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 w-[380px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {initialConfig ? 'Edit Filter' : 'Create Filter'}
        </h3>
        <button
          onClick={onCancel}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Label */}
        <div className="text-xs font-semibold uppercase tracking-wide text-purple-600 dark:text-purple-400">
          FILTER
        </div>

        {/* Selection type and count */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-700 dark:text-gray-300">Select</span>
          <select
            value={selection}
            onChange={(e) => setSelection(e.target.value as FilterSelection)}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            <option value="top">Top</option>
            <option value="bottom">Bottom</option>
          </select>
          <input
            type="number"
            value={count}
            onChange={(e) => setCount(Math.max(1, parseInt(e.target.value) || 1))}
            min={1}
            max={100}
            className="w-20 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">assets</span>
        </div>

        {/* Universe */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            From
          </label>
          <select
            value={universe}
            onChange={(e) => setUniverse(e.target.value as FilterUniverse)}
            className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {FILTER_UNIVERSES.map((u) => (
              <option key={u.value} value={u.value}>
                {u.label} - {u.description}
              </option>
            ))}
          </select>
        </div>

        {/* Custom symbols (if custom universe) */}
        {universe === 'custom' && (
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Custom Symbols (comma-separated)
            </label>
            <input
              type="text"
              value={customSymbols}
              onChange={(e) => setCustomSymbols(e.target.value)}
              placeholder="AAPL, MSFT, GOOGL, ..."
              className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
        )}

        {/* Sort by */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Sorted by
          </label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as FilterSortBy)}
            className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {FILTER_SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label} - {opt.description}
              </option>
            ))}
          </select>
        </div>

        {/* Period */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Period
          </label>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as FilterPeriod)}
            className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {FILTER_PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-3 py-1.5 text-sm bg-purple-500 hover:bg-purple-600 text-white rounded-md transition-colors"
        >
          {initialConfig ? 'Update' : 'Add Filter'}
        </button>
      </div>
    </div>
  );
}
