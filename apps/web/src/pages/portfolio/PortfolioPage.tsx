/**
 * Portfolio overview: identity header, KPI rail, equity curve, and the
 * strategies allocation & performance table.
 */

import { Loader2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { AddFundsModal } from '../../components/funding/AddFundsModal';
import {
  AllocationPanel,
  PortfolioHeader,
  PortfolioSummaryBar,
  PositionsBlotter,
  StrategyChart,
  StrategyList,
} from '../../components/portfolio';
import { useAuthStore } from '../../store/auth';
import { usePortfolioStore } from '../../store/portfolio';

// Prefer the real name; fall back to the email local-part ("alex.rivera" → "Alex Rivera").
function holderFrom(
  user: { firstName?: string; lastName?: string; email?: string } | null | undefined
): string {
  const full = [user?.firstName, user?.lastName].filter(Boolean).join(' ');
  if (full) return full;
  const local = user?.email?.split('@')[0];
  if (!local) return '';
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export default function PortfolioPage() {
  const user = useAuthStore((state) => state.user);
  const {
    strategies,
    portfolioCurve,
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
    freeCash,
    freeCashPercent,
    deployedValue,
    liveStrategiesCount,
    openPositionsCount,
    accountMode,
    marketStatus,
    marketNextOpen,
    marketNextClose,
    fetchPortfolio,
    fetchMarketStatus,
    setSelectedPeriod,
    setSelectedBenchmark,
    toggleStrategyExpanded,
    toggleStrategyVisibility,
    setHoveredStrategy,
    clearError,
  } = usePortfolioStore();

  const [fundOpen, setFundOpen] = useState(false);

  useEffect(() => {
    fetchPortfolio();
    fetchMarketStatus();
  }, [fetchPortfolio, fetchMarketStatus]);

  const holderName = useMemo(() => holderFrom(user), [user]);
  const accountRef = useMemo(
    () => (user?.tenantId ? user.tenantId.replace(/[^a-zA-Z0-9]/g, '').slice(0, 6).toUpperCase() : ''),
    [user?.tenantId]
  );

  if (loading && strategies.length === 0) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)] bg-bone bg-grid">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-orange-500 animate-spin" />
          <span className="text-xs font-mono uppercase tracking-wide text-ink/60">Loading portfolio...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)] bg-bone bg-grid">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="text-red-600 text-xs font-mono uppercase tracking-wide">{error}</div>
          <button
            onClick={() => {
              clearError();
              fetchPortfolio();
            }}
            className="btn btn-primary"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-56px)] bg-bone bg-grid overflow-y-auto">
      <div className="max-w-[1760px] mx-auto px-6 lg:px-8 py-7 flex flex-col gap-[18px]">
        <PortfolioHeader
          mode={accountMode}
          holderName={holderName}
          accountRef={accountRef}
          openPositions={openPositionsCount}
          marketStatus={marketStatus}
          marketNextOpen={marketNextOpen}
          marketNextClose={marketNextClose}
        />

        <PortfolioSummaryBar
          totalEquity={totalEquity}
          dayPnl={dayPnl}
          dayPnlPercent={dayPnlPercent}
          totalReturn={totalReturn}
          totalReturnPercent={totalReturnPercent}
          freeCash={freeCash}
          freeCashPercent={freeCashPercent}
          deployedValue={deployedValue}
          liveStrategiesCount={liveStrategiesCount}
          onAddFunds={() => setFundOpen(true)}
        />

        <AddFundsModal
          isOpen={fundOpen}
          onClose={() => setFundOpen(false)}
          onFunded={() => void fetchPortfolio()}
        />

        <StrategyChart
          strategies={strategies}
          portfolioCurve={portfolioCurve}
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

        <StrategyList
          strategies={strategies}
          totalBook={totalEquity}
          expandedStrategyId={expandedStrategyId}
          hoveredStrategyId={hoveredStrategyId}
          onToggleExpanded={toggleStrategyExpanded}
          onHoverStrategy={setHoveredStrategy}
        />

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr] gap-[18px] items-start">
          <AllocationPanel strategies={strategies} freeCash={freeCash} totalBook={totalEquity} />
          <PositionsBlotter strategies={strategies} />
        </div>
      </div>
    </div>
  );
}
