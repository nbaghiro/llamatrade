import { X } from 'lucide-react';
import { useState, useCallback } from 'react';

import type {
  FilterConfig,
  FilterSelection,
  FilterUniverse,
  FilterSortBy,
  FilterPeriod,
} from '@llamatrade/core/strategy/types';
import {
  FILTER_UNIVERSES,
  FILTER_SORT_OPTIONS,
  FILTER_PERIODS,
} from '@llamatrade/core/strategy/types';

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
    <div className="bg-paper border-2 border-ink shadow-lg w-[380px]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <h3 className="text-sm font-mono font-bold uppercase tracking-wide text-ink">
          {initialConfig ? 'Edit Filter' : 'Create Filter'}
        </h3>
        <button
          onClick={onCancel}
          className="p-1 hover:bg-ink/10"
        >
          <X className="w-4 h-4 text-ink/60" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="text-xs font-mono font-bold uppercase tracking-wide text-orange-600">
          FILTER
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-ink">Select</span>
          <select
            value={selection}
            onChange={(e) => setSelection(e.target.value as FilterSelection)}
            className="px-3 py-2 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:border-orange-500"
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
            className="w-20 px-3 py-2 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:border-orange-500"
          />
          <span className="text-sm text-ink">assets</span>
        </div>

        <div>
          <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">
            From
          </label>
          <select
            value={universe}
            onChange={(e) => setUniverse(e.target.value as FilterUniverse)}
            className="w-full px-3 py-2 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:border-orange-500"
          >
            {FILTER_UNIVERSES.map((u) => (
              <option key={u.value} value={u.value}>
                {u.label} - {u.description}
              </option>
            ))}
          </select>
        </div>

        {universe === 'custom' && (
          <div>
            <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">
              Custom Symbols (comma-separated)
            </label>
            <input
              type="text"
              value={customSymbols}
              onChange={(e) => setCustomSymbols(e.target.value)}
              placeholder="AAPL, MSFT, GOOGL, ..."
              className="w-full px-3 py-2 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:border-orange-500"
            />
          </div>
        )}

        <div>
          <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">
            Sorted by
          </label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as FilterSortBy)}
            className="w-full px-3 py-2 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:border-orange-500"
          >
            {FILTER_SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label} - {opt.description}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">
            Period
          </label>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as FilterPeriod)}
            className="w-full px-3 py-2 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:border-orange-500"
          >
            {FILTER_PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex justify-end gap-2 px-4 py-3 border-t-2 border-ink bg-bone">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-ink border-2 border-ink hover:bg-ink hover:text-bone transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-3 py-1.5 text-sm font-mono font-bold uppercase tracking-wide bg-orange-500 hover:bg-orange-600 text-ink border-2 border-ink transition-colors"
        >
          {initialConfig ? 'Update' : 'Add Filter'}
        </button>
      </div>
    </div>
  );
}
