/**
 * Portfolio Page
 * Shows strategy performance chart and scrollable strategy list.
 */

import { Loader2 } from 'lucide-react';
import { useEffect } from 'react';

import { PortfolioSummaryBar, StrategyChart, StrategyList } from '../../components/portfolio';
import { usePortfolioStore } from '../../store/portfolio';

export default function PortfolioPage() {
  const {
    strategies,
    benchmarkData,
    selectedPeriod,
    selectedBenchmark,
    expandedStrategyId,
    visibleStrategyIds,
    hoveredStrategyId,
    loading,
    error,
    totalEquity,
    dayPnl,
    dayPnlPercent,
    totalReturn,
    totalReturnPercent,
    fetchPortfolio,
    setSelectedPeriod,
    setSelectedBenchmark,
    toggleStrategyExpanded,
    toggleStrategyVisibility,
    setHoveredStrategy,
    clearError,
  } = usePortfolioStore();

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  if (loading && strategies.length === 0) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-green-500 animate-spin" />
          <span className="text-sm text-gray-500 dark:text-gray-400">Loading portfolio...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="text-red-500 dark:text-red-400 text-sm">{error}</div>
          <button
            onClick={() => {
              clearError();
              fetchPortfolio();
            }}
            className="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950 bg-dotted-grid overflow-y-auto">
      <div className="flex flex-col px-12 py-8 gap-4 min-h-full">
        {/* Summary Bar */}
        <PortfolioSummaryBar
          totalEquity={totalEquity}
          dayPnl={dayPnl}
          dayPnlPercent={dayPnlPercent}
          totalReturn={totalReturn}
          totalReturnPercent={totalReturnPercent}
        />

        {/* Chart */}
        <StrategyChart
          strategies={strategies}
          benchmarkData={benchmarkData}
          selectedPeriod={selectedPeriod}
          selectedBenchmark={selectedBenchmark}
          visibleStrategyIds={visibleStrategyIds}
          hoveredStrategyId={hoveredStrategyId}
          onPeriodChange={setSelectedPeriod}
          onBenchmarkChange={setSelectedBenchmark}
          onToggleVisibility={toggleStrategyVisibility}
          onHoverStrategy={setHoveredStrategy}
        />

        {/* Strategy List - grows to fill remaining space */}
        <div className="flex-1">
          <StrategyList
            strategies={strategies}
            selectedPeriod={selectedPeriod}
            expandedStrategyId={expandedStrategyId}
            visibleStrategyIds={visibleStrategyIds}
            hoveredStrategyId={hoveredStrategyId}
            onToggleExpanded={toggleStrategyExpanded}
            onToggleVisibility={toggleStrategyVisibility}
            onHoverStrategy={setHoveredStrategy}
          />
        </div>
      </div>
    </div>
  );
}
