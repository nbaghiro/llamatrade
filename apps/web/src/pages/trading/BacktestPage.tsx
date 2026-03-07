/**
 * Backtest Page
 * Main page for running and viewing backtests.
 * Features sample ETF charts and backtest configuration.
 */

import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  DollarSign,
  Loader2,
  Play,
  RefreshCw,
  Search,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import BacktestProgress from '../../components/backtest/BacktestProgress';
import EquityCurveChart from '../../components/backtest/EquityCurveChart';
import MetricsPanel from '../../components/backtest/MetricsPanel';
import MonthlyReturnsGrid from '../../components/backtest/MonthlyReturnsGrid';
import StrategyPickerModal from '../../components/backtest/StrategyPickerModal';
import TradesTable from '../../components/backtest/TradesTable';
import { BacktestStatus } from '../../generated/proto/backtest_pb';
import type { Strategy } from '../../generated/proto/strategy_pb';
import { useBacktestStore, toNumber } from '../../store/backtest';

type ResultsTab = 'trades' | 'monthly';

// Featured ETF data with realistic performance
const FEATURED_ETFS = [
  {
    symbol: 'SPY',
    name: 'S&P 500 ETF',
    description: 'Broad US market exposure tracking 500 large-cap stocks',
    return1M: 3.2,
    return1Y: 24.8,
    sharpe: 1.42,
    maxDrawdown: -5.2,
    color: '#3b82f6', // blue
  },
  {
    symbol: 'QQQ',
    name: 'Nasdaq 100 ETF',
    description: 'Tech-heavy growth stocks with high momentum',
    return1M: 4.1,
    return1Y: 31.5,
    sharpe: 1.28,
    maxDrawdown: -8.4,
    color: '#8b5cf6', // purple
  },
  {
    symbol: 'IWM',
    name: 'Russell 2000 ETF',
    description: 'Small-cap diversification for higher growth potential',
    return1M: 2.8,
    return1Y: 18.2,
    sharpe: 0.95,
    maxDrawdown: -12.1,
    color: '#22c55e', // green
  },
  {
    symbol: 'DIA',
    name: 'Dow Jones ETF',
    description: 'Blue-chip industrials with stable dividends',
    return1M: 2.1,
    return1Y: 19.4,
    sharpe: 1.18,
    maxDrawdown: -4.8,
    color: '#f59e0b', // amber
  },
];

// Generate realistic chart data for an ETF
function generateChartData(symbol: string, points: number = 30): number[] {
  const seed = symbol.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const data: number[] = [];
  let value = 100;

  for (let i = 0; i < points; i++) {
    const trend = 0.002 + (seed % 10) * 0.0003;
    const volatility = 0.015 + (seed % 5) * 0.003;
    const noise = Math.sin(seed * i * 0.1) * volatility;
    value = value * (1 + trend + noise);
    data.push(value);
  }
  return data;
}

// Generate benchmark data (SPY-like)
function generateBenchmarkData(points: number = 30): number[] {
  const data: number[] = [];
  let value = 100;
  for (let i = 0; i < points; i++) {
    value = value * (1 + 0.0015 + Math.sin(i * 0.15) * 0.008);
    data.push(value);
  }
  return data;
}

interface ETFChartCardProps {
  etf: typeof FEATURED_ETFS[0];
  onClick: () => void;
}

function ETFChartCard({ etf, onClick }: ETFChartCardProps) {
  const chartData = useMemo(() => generateChartData(etf.symbol), [etf.symbol]);
  const benchmarkData = useMemo(() => generateBenchmarkData(), []);
  const isPositive = chartData[chartData.length - 1] > chartData[0];

  // Calculate chart points
  const allValues = [...chartData, ...benchmarkData];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  const toPoints = (values: number[], width: number, height: number) =>
    values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = height - ((v - min) / range) * (height - 8);
        return `${x},${y}`;
      })
      .join(' ');

  const height = 100;
  const gradientId = `gradient-${etf.symbol}`;

  return (
    <button
      onClick={onClick}
      className="group text-left rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-primary-400 dark:hover:border-primary-500 hover:shadow-lg transition-all overflow-hidden flex flex-col"
    >
      {/* Chart Section */}
      <div className="relative bg-gray-50 dark:bg-gray-800/50 p-4 pb-0">
        <svg viewBox={`0 0 200 ${height}`} preserveAspectRatio="none" className="w-full h-24">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={etf.color} stopOpacity="0.2" />
              <stop offset="100%" stopColor={etf.color} stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* Area fill */}
          <polygon
            points={`0,${height} ${toPoints(chartData, 200, height)} 200,${height}`}
            fill={`url(#${gradientId})`}
          />
          {/* Benchmark line */}
          <polyline
            points={toPoints(benchmarkData, 200, height)}
            fill="none"
            stroke="#9ca3af"
            strokeWidth="1"
            strokeDasharray="3,2"
            vectorEffect="non-scaling-stroke"
          />
          {/* Main line */}
          <polyline
            points={toPoints(chartData, 200, height)}
            fill="none"
            stroke={etf.color}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>

      {/* Content Section */}
      <div className="p-4 flex-1 flex flex-col">
        {/* Stats Row */}
        <div className="flex items-center gap-4 mb-3 text-sm">
          <div>
            <span className={`font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
              {isPositive ? '+' : ''}{etf.return1M.toFixed(1)}%
            </span>
            <span className="text-gray-400 dark:text-gray-500 ml-1 text-xs">1M</span>
          </div>
          <div>
            <span className="font-semibold text-gray-700 dark:text-gray-300">
              {etf.sharpe.toFixed(2)}
            </span>
            <span className="text-gray-400 dark:text-gray-500 ml-1 text-xs">Sharpe</span>
          </div>
          <div>
            <span className="font-semibold text-red-500">{etf.maxDrawdown.toFixed(1)}%</span>
            <span className="text-gray-400 dark:text-gray-500 ml-1 text-xs">Max DD</span>
          </div>
        </div>

        {/* Title */}
        <div className="flex items-start justify-between gap-2 mb-1">
          <div className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: etf.color }}
            />
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
              {etf.symbol}
            </h3>
            <span className="text-sm text-gray-500 dark:text-gray-400">{etf.name}</span>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-1">
          {etf.description}
        </p>
      </div>
    </button>
  );
}

export default function BacktestPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [strategyPickerOpen, setStrategyPickerOpen] = useState(false);
  const [resultsTab, setResultsTab] = useState<ResultsTab>('trades');
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [symbolInput, setSymbolInput] = useState('');

  const {
    currentBacktest,
    config,
    setConfig,
    loading,
    progress,
    progressMessage,
    error,
    runBacktest,
    getBacktest,
    cancelBacktest,
    clearError,
    reset,
  } = useBacktestStore();

  // Get strategy ID from URL query param
  const strategyId = searchParams.get('strategy') ?? undefined;

  // Load backtest from URL if present
  useEffect(() => {
    const backtestId = searchParams.get('id');
    if (backtestId && !currentBacktest) {
      getBacktest(backtestId);
    }
  }, [searchParams, currentBacktest, getBacktest]);

  // Set initial strategy from URL param
  useEffect(() => {
    if (strategyId && !config.strategyId) {
      setConfig({ strategyId });
    }
  }, [strategyId, config.strategyId, setConfig]);

  // Handle strategy selection from picker
  const handleStrategySelect = (strategy: Strategy) => {
    setSelectedStrategy(strategy);
    setConfig({ strategyId: strategy.id });
  };

  // Handle running a new backtest
  const handleRunBacktest = async () => {
    const backtestId = await runBacktest();
    if (backtestId) {
      setSearchParams({ id: backtestId });
    }
  };

  // Handle starting a new backtest
  const handleNewBacktest = () => {
    reset();
    setSelectedStrategy(null);
    setSymbolInput('');
    setSearchParams({});
  };

  // Handle ETF card click - prefill with symbol and date range
  const handleETFClick = (symbol: string) => {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 1);

    setSymbolInput(symbol);
    setConfig({
      symbols: [symbol],
      startDate: startDate.toISOString().split('T')[0],
      endDate: endDate.toISOString().split('T')[0],
    });
  };

  // Handle symbol input change
  const handleSymbolChange = (value: string) => {
    setSymbolInput(value.toUpperCase());
    if (value) {
      setConfig({ symbols: [value.toUpperCase()] });
    }
  };

  // Determine current view state
  const isRunning =
    currentBacktest?.status === BacktestStatus.RUNNING ||
    currentBacktest?.status === BacktestStatus.PENDING;
  const isCompleted = currentBacktest?.status === BacktestStatus.COMPLETED;
  const isFailed = currentBacktest?.status === BacktestStatus.FAILED;
  const hasResults = isCompleted && currentBacktest?.results;

  // Validation - either strategy or symbol required
  const isConfigValid =
    (config.strategyId || (config.symbols && config.symbols.length > 0)) &&
    config.startDate &&
    config.endDate;

  return (
    <div className="min-h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950 bg-dotted-grid overflow-y-auto">
      <div className="px-12 py-8">
        {/* New Backtest button - only shown when viewing results */}
        {(currentBacktest || isRunning) && (
          <div className="flex justify-end mb-4">
            <button
              onClick={handleNewBacktest}
              className="flex items-center gap-2 px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              New Backtest
            </button>
          </div>
        )}

        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
            <button
              onClick={clearError}
              className="px-3 py-1.5 text-sm text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Main Content - Featured ETFs + Config when not running */}
        {!isRunning && !hasResults && (
          <>
            {/* Featured ETF Charts */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Quick Start
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {FEATURED_ETFS.map((etf) => (
                  <ETFChartCard
                    key={etf.symbol}
                    etf={etf}
                    onClick={() => handleETFClick(etf.symbol)}
                  />
                ))}
              </div>
            </div>

            {/* Backtest Configuration */}
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
              {/* Row 1: Symbol/Strategy + Date Range */}
              <div className="flex flex-col lg:flex-row gap-4 mb-4">
                {/* Symbol Input */}
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                    Symbol
                  </label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      value={symbolInput}
                      onChange={(e) => handleSymbolChange(e.target.value)}
                      placeholder="AAPL, MSFT..."
                      className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:bg-white dark:focus:bg-gray-900 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                    />
                  </div>
                </div>

                {/* Divider */}
                <div className="hidden lg:flex items-end pb-2">
                  <span className="text-xs text-gray-400 font-medium">or</span>
                </div>

                {/* Strategy Picker */}
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                    Strategy
                  </label>
                  <button
                    onClick={() => setStrategyPickerOpen(true)}
                    className="w-full flex items-center justify-between px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800/50 hover:bg-white dark:hover:bg-gray-900 hover:border-primary-500 transition-colors"
                  >
                    <span
                      className={
                        selectedStrategy
                          ? 'text-gray-900 dark:text-gray-100'
                          : 'text-gray-400'
                      }
                    >
                      {selectedStrategy?.name || 'Select strategy...'}
                    </span>
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  </button>
                </div>

                {/* Vertical Divider */}
                <div className="hidden lg:block w-px bg-gray-200 dark:bg-gray-700 my-1" />

                {/* Date Range */}
                <div className="flex gap-3">
                  <div className="w-36">
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                      From
                    </label>
                    <input
                      type="date"
                      value={config.startDate}
                      onChange={(e) => setConfig({ startDate: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 focus:bg-white dark:focus:bg-gray-900 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                    />
                  </div>
                  <div className="w-36">
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                      To
                    </label>
                    <input
                      type="date"
                      value={config.endDate}
                      onChange={(e) => setConfig({ endDate: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 focus:bg-white dark:focus:bg-gray-900 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                    />
                  </div>
                </div>
              </div>

              {/* Row 2: Capital + Timeframe + Run Button */}
              <div className="flex flex-col sm:flex-row items-end gap-4 pt-4 border-t border-gray-100 dark:border-gray-800">
                {/* Initial Capital */}
                <div className="w-full sm:w-40">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                    Capital
                  </label>
                  <div className="relative">
                    <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="number"
                      value={config.initialCapital}
                      onChange={(e) =>
                        setConfig({ initialCapital: parseFloat(e.target.value) || 0 })
                      }
                      min={0}
                      step={1000}
                      className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 focus:bg-white dark:focus:bg-gray-900 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                    />
                  </div>
                </div>

                {/* Timeframe */}
                <div className="w-full sm:w-32">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                    Timeframe
                  </label>
                  <div className="relative">
                    <select
                      value={config.timeframe}
                      onChange={(e) => setConfig({ timeframe: e.target.value })}
                      className="w-full appearance-none px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 focus:bg-white dark:focus:bg-gray-900 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors cursor-pointer"
                    >
                      <option value="1Min">1 Min</option>
                      <option value="5Min">5 Min</option>
                      <option value="15Min">15 Min</option>
                      <option value="1H">1 Hour</option>
                      <option value="4H">4 Hour</option>
                      <option value="1D">1 Day</option>
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                  </div>
                </div>

                {/* Spacer */}
                <div className="hidden sm:block flex-1" />

                {/* Run Button */}
                <button
                  onClick={handleRunBacktest}
                  disabled={loading || !isConfigValid}
                  className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-medium transition-colors disabled:cursor-not-allowed"
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
            </div>
          </>
        )}

        {/* Progress - shown when running */}
        {isRunning && currentBacktest && (
          <div className="mb-6">
            <BacktestProgress
              backtest={currentBacktest}
              progress={progress}
              message={progressMessage}
              onCancel={() => cancelBacktest(currentBacktest.id)}
            />
          </div>
        )}

        {/* Failed State */}
        {isFailed && currentBacktest && (
          <div className="mb-6 p-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" />
              <div>
                <h3 className="font-medium text-red-800 dark:text-red-200">Backtest Failed</h3>
                <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                  {currentBacktest.statusMessage || 'An error occurred during the backtest.'}
                </p>
                <button
                  onClick={handleNewBacktest}
                  className="mt-3 px-4 py-2 text-sm bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Results - shown when completed */}
        {hasResults && currentBacktest.results && (
          <div className="space-y-6">
            {/* Strategy Info */}
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Strategy</p>
                  <p className="font-medium text-gray-900 dark:text-gray-100">
                    {currentBacktest.config?.strategyId}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-500 dark:text-gray-400">Initial Capital</p>
                  <p className="font-mono font-medium text-gray-900 dark:text-gray-100">
                    ${toNumber(currentBacktest.config?.initialCapital).toLocaleString()}
                  </p>
                </div>
              </div>
            </div>

            {/* Metrics Panel */}
            {currentBacktest.results.metrics && (
              <MetricsPanel metrics={currentBacktest.results.metrics} />
            )}

            {/* Equity Curve */}
            {currentBacktest.results.equityCurve.length > 0 && (
              <EquityCurveChart
                data={currentBacktest.results.equityCurve}
                initialCapital={toNumber(currentBacktest.config?.initialCapital) || 100000}
              />
            )}

            {/* Tabs for Trades and Monthly Returns */}
            <div>
              <div className="flex items-center gap-1 mb-4 border-b border-gray-200 dark:border-gray-800">
                <button
                  onClick={() => setResultsTab('trades')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    resultsTab === 'trades'
                      ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  Trades
                </button>
                <button
                  onClick={() => setResultsTab('monthly')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    resultsTab === 'monthly'
                      ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  Monthly Returns
                </button>
              </div>

              {resultsTab === 'trades' && (
                <TradesTable trades={currentBacktest.results.trades} />
              )}

              {resultsTab === 'monthly' && (
                <MonthlyReturnsGrid monthlyReturns={currentBacktest.results.monthlyReturns} />
              )}
            </div>
          </div>
        )}

        {/* Modals */}
        <StrategyPickerModal
          isOpen={strategyPickerOpen}
          onClose={() => setStrategyPickerOpen(false)}
          onSelect={handleStrategySelect}
          selectedId={config.strategyId}
        />
      </div>
    </div>
  );
}
