/**
 * Backtest Configuration Form
 * Allows users to configure and run backtests.
 */

import { Calendar, ChevronDown, Loader2, Play, Settings, DollarSign } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useBacktestStore } from '../../store/backtest';

interface BacktestConfigFormProps {
  initialStrategyId?: string;
  onSubmit: () => void;
  loading: boolean;
}

const TIMEFRAMES = [
  { value: '1Min', label: '1 Minute' },
  { value: '5Min', label: '5 Minutes' },
  { value: '15Min', label: '15 Minutes' },
  { value: '1H', label: '1 Hour' },
  { value: '4H', label: '4 Hours' },
  { value: '1D', label: '1 Day' },
];

export default function BacktestConfigForm({
  initialStrategyId,
  onSubmit,
  loading,
}: BacktestConfigFormProps) {
  const {
    config,
    setConfig,
    strategies,
    strategiesLoading,
    fetchStrategies,
  } = useBacktestStore();

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [symbolsInput, setSymbolsInput] = useState(config.symbols.join(', '));

  // Fetch strategies on mount
  useEffect(() => {
    fetchStrategies();
  }, [fetchStrategies]);

  // Set initial strategy from URL param
  useEffect(() => {
    if (initialStrategyId && !config.strategyId) {
      setConfig({ strategyId: initialStrategyId });
    }
  }, [initialStrategyId, config.strategyId, setConfig]);

  // Update symbols when input changes
  const handleSymbolsChange = (value: string) => {
    setSymbolsInput(value);
    const symbols = value
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    setConfig({ symbols });
  };

  // Validation
  const isValid = (): boolean => {
    if (!config.strategyId) return false;
    const start = new Date(config.startDate);
    const end = new Date(config.endDate);
    if (end <= start) return false;
    if (config.initialCapital <= 0) return false;
    return true;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isValid()) {
      onSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Main Config Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Strategy Selector */}
        <div>
          <label
            htmlFor="strategy"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
          >
            Strategy
          </label>
          <div className="relative">
            <select
              id="strategy"
              value={config.strategyId}
              onChange={(e) => setConfig({ strategyId: e.target.value })}
              disabled={strategiesLoading}
              className="w-full appearance-none px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none disabled:opacity-50"
            >
              <option value="">
                {strategiesLoading
                  ? 'Loading strategies...'
                  : strategies.length === 0
                    ? 'No strategies available'
                    : 'Select a strategy'}
              </option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            {strategiesLoading && (
              <Loader2 className="absolute right-8 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
            )}
          </div>
          {!strategiesLoading && strategies.length === 0 && (
            <div className="mt-1.5 flex items-center gap-2">
              <p className="text-xs text-amber-600 dark:text-amber-400">
                No strategies found.
              </p>
              <button
                type="button"
                onClick={() => fetchStrategies()}
                className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
              >
                Retry
              </button>
            </div>
          )}
        </div>

        {/* Start Date */}
        <div>
          <label
            htmlFor="startDate"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
          >
            Start Date
          </label>
          <div className="relative">
            <input
              type="date"
              id="startDate"
              value={config.startDate}
              onChange={(e) => setConfig({ startDate: e.target.value })}
              className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
            <Calendar className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>

        {/* End Date */}
        <div>
          <label
            htmlFor="endDate"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
          >
            End Date
          </label>
          <div className="relative">
            <input
              type="date"
              id="endDate"
              value={config.endDate}
              onChange={(e) => setConfig({ endDate: e.target.value })}
              className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
            <Calendar className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>

        {/* Initial Capital */}
        <div>
          <label
            htmlFor="capital"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
          >
            Initial Capital
          </label>
          <div className="relative">
            <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="number"
              id="capital"
              value={config.initialCapital}
              onChange={(e) => setConfig({ initialCapital: parseFloat(e.target.value) || 0 })}
              min={0}
              step={1000}
              className="w-full pl-9 pr-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>
        </div>
      </div>

      {/* Symbols Input */}
      <div>
        <label
          htmlFor="symbols"
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
        >
          Symbols{' '}
          <span className="font-normal text-gray-400">(optional, uses strategy defaults if empty)</span>
        </label>
        <input
          type="text"
          id="symbols"
          value={symbolsInput}
          onChange={(e) => handleSymbolsChange(e.target.value)}
          placeholder="AAPL, MSFT, GOOGL"
          className="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
        />
      </div>

      {/* Advanced Settings Toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
      >
        <Settings className="w-4 h-4" />
        Advanced Settings
        <ChevronDown
          className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Advanced Settings Panel */}
      {showAdvanced && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
          {/* Timeframe */}
          <div>
            <label
              htmlFor="timeframe"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
            >
              Timeframe
            </label>
            <div className="relative">
              <select
                id="timeframe"
                value={config.timeframe}
                onChange={(e) => setConfig({ timeframe: e.target.value })}
                className="w-full appearance-none px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value}>
                    {tf.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Commission */}
          <div>
            <label
              htmlFor="commission"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
            >
              Commission (%)
            </label>
            <input
              type="number"
              id="commission"
              value={config.commission * 100}
              onChange={(e) => setConfig({ commission: (parseFloat(e.target.value) || 0) / 100 })}
              min={0}
              max={10}
              step={0.01}
              className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>

          {/* Slippage */}
          <div>
            <label
              htmlFor="slippage"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
            >
              Slippage (%)
            </label>
            <input
              type="number"
              id="slippage"
              value={config.slippage * 100}
              onChange={(e) => setConfig({ slippage: (parseFloat(e.target.value) || 0) / 100 })}
              min={0}
              max={10}
              step={0.01}
              className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>
        </div>
      )}

      {/* Submit Button */}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={loading || !isValid()}
          className="flex items-center gap-2 px-6 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white rounded-lg font-medium transition-colors shadow-sm disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Starting...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run Backtest
            </>
          )}
        </button>
      </div>
    </form>
  );
}
