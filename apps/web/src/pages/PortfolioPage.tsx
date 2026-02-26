import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  Clock,
  DollarSign,
  PieChart,
  TrendingUp,
} from 'lucide-react';
import { useState } from 'react';

// Demo data - will be replaced with API calls
const demoSummary = {
  totalEquity: 127843.52,
  cash: 15234.18,
  marketValue: 112609.34,
  totalUnrealizedPnl: 12843.52,
  totalRealizedPnl: 8420.0,
  dayPnl: 1247.83,
  dayPnlPercent: 0.98,
  totalPnlPercent: 11.18,
  positionsCount: 8,
};

const demoPositions = [
  {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    qty: 50,
    side: 'long',
    costBasis: 8750.0,
    marketValue: 9625.0,
    unrealizedPnl: 875.0,
    unrealizedPnlPercent: 10.0,
    currentPrice: 192.5,
    avgEntryPrice: 175.0,
    allocation: 8.55,
  },
  {
    symbol: 'MSFT',
    name: 'Microsoft Corp.',
    qty: 30,
    side: 'long',
    costBasis: 11100.0,
    marketValue: 12450.0,
    unrealizedPnl: 1350.0,
    unrealizedPnlPercent: 12.16,
    currentPrice: 415.0,
    avgEntryPrice: 370.0,
    allocation: 11.06,
  },
  {
    symbol: 'GOOGL',
    name: 'Alphabet Inc.',
    qty: 25,
    side: 'long',
    costBasis: 3500.0,
    marketValue: 3875.0,
    unrealizedPnl: 375.0,
    unrealizedPnlPercent: 10.71,
    currentPrice: 155.0,
    avgEntryPrice: 140.0,
    allocation: 3.44,
  },
  {
    symbol: 'NVDA',
    name: 'NVIDIA Corp.',
    qty: 20,
    side: 'long',
    costBasis: 14000.0,
    marketValue: 17600.0,
    unrealizedPnl: 3600.0,
    unrealizedPnlPercent: 25.71,
    currentPrice: 880.0,
    avgEntryPrice: 700.0,
    allocation: 15.63,
  },
  {
    symbol: 'AMZN',
    name: 'Amazon.com Inc.',
    qty: 40,
    side: 'long',
    costBasis: 6800.0,
    marketValue: 7200.0,
    unrealizedPnl: 400.0,
    unrealizedPnlPercent: 5.88,
    currentPrice: 180.0,
    avgEntryPrice: 170.0,
    allocation: 6.39,
  },
  {
    symbol: 'SPY',
    name: 'SPDR S&P 500 ETF',
    qty: 100,
    side: 'long',
    costBasis: 48000.0,
    marketValue: 50200.0,
    unrealizedPnl: 2200.0,
    unrealizedPnlPercent: 4.58,
    currentPrice: 502.0,
    avgEntryPrice: 480.0,
    allocation: 44.58,
  },
  {
    symbol: 'QQQ',
    name: 'Invesco QQQ Trust',
    qty: 15,
    side: 'long',
    costBasis: 6300.0,
    marketValue: 6659.34,
    unrealizedPnl: 359.34,
    unrealizedPnlPercent: 5.7,
    currentPrice: 443.96,
    avgEntryPrice: 420.0,
    allocation: 5.91,
  },
  {
    symbol: 'TSLA',
    name: 'Tesla Inc.',
    qty: 25,
    side: 'long',
    costBasis: 5500.0,
    marketValue: 5000.0,
    unrealizedPnl: -500.0,
    unrealizedPnlPercent: -9.09,
    currentPrice: 200.0,
    avgEntryPrice: 220.0,
    allocation: 4.44,
  },
];

const demoMetrics = {
  period: '1M',
  totalReturn: 12843.52,
  totalReturnPercent: 11.18,
  annualizedReturn: 42.5,
  volatility: 18.2,
  sharpeRatio: 1.85,
  sortinoRatio: 2.42,
  maxDrawdown: -8.5,
  winRate: 68.5,
  profitFactor: 2.1,
  bestDay: 3.2,
  worstDay: -2.1,
  avgDailyReturn: 0.45,
};

// Generate demo equity curve data
const generateEquityCurve = () => {
  const points = [];
  const now = new Date();
  let equity = 100000;

  for (let i = 30; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    // Add some realistic volatility
    const change = (Math.random() - 0.45) * 2000;
    equity = Math.max(equity + change, 90000);
    points.push({
      date: date.toISOString().split('T')[0],
      equity: equity,
    });
  }
  // Ensure last point matches our demo total
  points[points.length - 1].equity = demoSummary.totalEquity;
  return points;
};

const demoEquityCurve = generateEquityCurve();

type Period = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | 'YTD' | 'ALL';

export default function PortfolioPage() {
  const [selectedPeriod, setSelectedPeriod] = useState<Period>('1M');
  const [isMetricsOpen, setIsMetricsOpen] = useState(true);
  const [isAllocationOpen, setIsAllocationOpen] = useState(true);

  const periods: Period[] = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'];

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  };

  const formatNumber = (value: number, decimals = 2) => {
    return value.toFixed(decimals);
  };

  // Calculate SVG path for equity curve
  const getEquityCurvePath = () => {
    const minEquity = Math.min(...demoEquityCurve.map((p) => p.equity));
    const maxEquity = Math.max(...demoEquityCurve.map((p) => p.equity));
    const range = maxEquity - minEquity || 1;

    const points = demoEquityCurve.map((point, i) => {
      const x = (i / (demoEquityCurve.length - 1)) * 400;
      const y = 120 - ((point.equity - minEquity) / range) * 100;
      return `${x},${y}`;
    });

    return `M ${points.join(' L ')}`;
  };

  const getAreaPath = () => {
    const path = getEquityCurvePath();
    return `${path} L 400,120 L 0,120 Z`;
  };

  return (
    <div className="flex h-[calc(100vh-56px)] overflow-hidden bg-gray-50 dark:bg-gray-950 bg-dotted-grid p-6 gap-6">
      {/* Left Panel - Account Overview */}
      <div className="w-[320px] flex-shrink-0 flex flex-col gap-3 p-4 overflow-y-auto">
        {/* Total Equity Card */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
            <DollarSign className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wide">Total Equity</span>
          </div>
          <div className="text-2xl font-semibold text-gray-900 dark:text-gray-100 font-data">
            {formatCurrency(demoSummary.totalEquity)}
          </div>
          <div className="flex items-center gap-1 mt-1">
            {demoSummary.dayPnl >= 0 ? (
              <ArrowUpRight className="w-4 h-4 text-green-500" />
            ) : (
              <ArrowDownRight className="w-4 h-4 text-red-500" />
            )}
            <span
              className={`text-sm font-medium font-data ${demoSummary.dayPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
            >
              {formatCurrency(Math.abs(demoSummary.dayPnl))} ({formatPercent(demoSummary.dayPnlPercent)})
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">today</span>
          </div>
        </div>

        {/* Cash & Market Value */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-3 shadow-sm">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Cash</div>
            <div className="text-sm font-medium text-gray-900 dark:text-gray-100 font-data">
              {formatCurrency(demoSummary.cash)}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-3 shadow-sm">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Invested</div>
            <div className="text-sm font-medium text-gray-900 dark:text-gray-100 font-data">
              {formatCurrency(demoSummary.marketValue)}
            </div>
          </div>
        </div>

        {/* P&L Summary */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-3">
            <TrendingUp className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wide">Profit & Loss</span>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500 dark:text-gray-400">Unrealized</span>
              <span
                className={`text-sm font-medium font-data ${demoSummary.totalUnrealizedPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
              >
                {formatCurrency(demoSummary.totalUnrealizedPnl)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500 dark:text-gray-400">Realized</span>
              <span
                className={`text-sm font-medium font-data ${demoSummary.totalRealizedPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
              >
                {formatCurrency(demoSummary.totalRealizedPnl)}
              </span>
            </div>
            <div className="pt-2 border-t border-gray-100 dark:border-gray-800 flex justify-between items-center">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Total Return</span>
              <span
                className={`text-sm font-semibold font-data ${demoSummary.totalPnlPercent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
              >
                {formatPercent(demoSummary.totalPnlPercent)}
              </span>
            </div>
          </div>
        </div>

        {/* Allocation Breakdown */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
          <button
            onClick={() => setIsAllocationOpen(!isAllocationOpen)}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div className="flex items-center gap-2">
              <PieChart className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Allocation</span>
            </div>
            <ChevronDown
              className={`w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform ${isAllocationOpen ? '' : '-rotate-90'}`}
            />
          </button>
          {isAllocationOpen && (
            <div className="px-4 pb-3 space-y-2">
              {demoPositions
                .sort((a, b) => b.allocation - a.allocation)
                .slice(0, 5)
                .map((pos) => (
                  <div key={pos.symbol} className="flex items-center gap-2">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="font-medium text-gray-700 dark:text-gray-300">{pos.symbol}</span>
                        <span className="text-gray-500 dark:text-gray-400 font-data">
                          {pos.allocation.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-green-500 rounded-full"
                          style={{ width: `${pos.allocation}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              <div className="pt-1 text-xs text-gray-400 dark:text-gray-500 text-center">
                +{demoPositions.length - 5} more positions
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Center - Chart & Holdings */}
      <div className="flex-1 min-w-0 flex flex-col gap-4 overflow-auto pt-4 px-6 pb-24">
        {/* Equity Chart */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
          {/* Period Selector */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Portfolio Value</span>
            <div className="flex gap-1">
              {periods.map((period) => (
                <button
                  key={period}
                  onClick={() => setSelectedPeriod(period)}
                  className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                    selectedPeriod === period
                      ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  }`}
                >
                  {period}
                </button>
              ))}
            </div>
          </div>

          {/* Chart */}
          <div className="p-4">
            <div className="h-48 relative">
              <svg viewBox="0 0 400 120" className="w-full h-full" preserveAspectRatio="none">
                {/* Grid lines */}
                <g stroke="#e5e5e5" strokeWidth="0.5" className="dark:stroke-gray-700">
                  <line x1="0" y1="30" x2="400" y2="30" />
                  <line x1="0" y1="60" x2="400" y2="60" />
                  <line x1="0" y1="90" x2="400" y2="90" />
                </g>

                {/* Area fill */}
                <path d={getAreaPath()} fill="url(#portfolioGradient)" opacity="0.3" />

                {/* Line */}
                <path d={getEquityCurvePath()} fill="none" stroke="#22c55e" strokeWidth="2" />

                <defs>
                  <linearGradient id="portfolioGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                  </linearGradient>
                </defs>
              </svg>
            </div>

            {/* Chart footer */}
            <div className="flex items-center justify-between mt-2 text-xs text-gray-400 dark:text-gray-500">
              <span>30 days ago</span>
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>Updated just now</span>
              </div>
              <span>Today</span>
            </div>
          </div>
        </div>

        {/* Holdings Table */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Holdings ({demoSummary.positionsCount})
            </span>
          </div>

          <div className="overflow-auto flex-1">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
                <tr className="text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2 text-right">Shares</th>
                  <th className="px-4 py-2 text-right">Price</th>
                  <th className="px-4 py-2 text-right">Avg Cost</th>
                  <th className="px-4 py-2 text-right">Market Value</th>
                  <th className="px-4 py-2 text-right">P&L</th>
                  <th className="px-4 py-2 text-right">Return</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {demoPositions.map((position) => (
                  <tr
                    key={position.symbol}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div>
                        <div className="font-medium text-gray-900 dark:text-gray-100">{position.symbol}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">{position.name}</div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-data text-gray-900 dark:text-gray-100">
                      {position.qty}
                    </td>
                    <td className="px-4 py-3 text-right font-data text-gray-900 dark:text-gray-100">
                      {formatCurrency(position.currentPrice)}
                    </td>
                    <td className="px-4 py-3 text-right font-data text-gray-500 dark:text-gray-400">
                      {formatCurrency(position.avgEntryPrice)}
                    </td>
                    <td className="px-4 py-3 text-right font-data text-gray-900 dark:text-gray-100">
                      {formatCurrency(position.marketValue)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-data font-medium ${position.unrealizedPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
                    >
                      {position.unrealizedPnl >= 0 ? '+' : ''}
                      {formatCurrency(position.unrealizedPnl)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-data font-medium ${position.unrealizedPnlPercent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
                    >
                      {formatPercent(position.unrealizedPnlPercent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Right Panel - Performance Metrics */}
      <div className="w-[420px] flex-shrink-0 flex flex-col gap-3 p-4 overflow-y-auto">
        {/* Performance Metrics */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
          <button
            onClick={() => setIsMetricsOpen(!isMetricsOpen)}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Performance Metrics</span>
            <ChevronDown
              className={`w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform ${isMetricsOpen ? '' : '-rotate-90'}`}
            />
          </button>

          {isMetricsOpen && (
            <div className="px-4 pb-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Total Return</span>
                <span
                  className={`text-sm font-medium font-data ${demoMetrics.totalReturnPercent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
                >
                  {formatPercent(demoMetrics.totalReturnPercent)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Annualized Return</span>
                <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                  {formatPercent(demoMetrics.annualizedReturn)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Volatility</span>
                <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                  {formatNumber(demoMetrics.volatility)}%
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Sharpe Ratio</span>
                <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                  {formatNumber(demoMetrics.sharpeRatio)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Sortino Ratio</span>
                <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                  {formatNumber(demoMetrics.sortinoRatio)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Max Drawdown</span>
                <span className="text-sm font-medium font-data text-red-600 dark:text-red-400">
                  {formatNumber(demoMetrics.maxDrawdown)}%
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Win Rate</span>
                <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                  {formatNumber(demoMetrics.winRate)}%
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500 dark:text-gray-400">Profit Factor</span>
                <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                  {formatNumber(demoMetrics.profitFactor)}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Daily Stats */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Daily Stats</h3>
          <div className="space-y-2.5">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500 dark:text-gray-400">Best Day</span>
              <span className="text-sm font-medium font-data text-green-600 dark:text-green-400">
                +{formatNumber(demoMetrics.bestDay)}%
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500 dark:text-gray-400">Worst Day</span>
              <span className="text-sm font-medium font-data text-red-600 dark:text-red-400">
                {formatNumber(demoMetrics.worstDay)}%
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500 dark:text-gray-400">Avg Daily Return</span>
              <span className="text-sm font-medium font-data text-gray-900 dark:text-gray-100">
                {formatPercent(demoMetrics.avgDailyReturn)}
              </span>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Quick Actions</h3>
          <div className="space-y-2">
            <button className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 text-green-700 dark:text-green-400 font-medium transition-colors border border-green-200 dark:border-green-800 text-sm">
              <TrendingUp className="w-4 h-4" />
              Deposit Funds
            </button>
            <button className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 transition-colors text-sm">
              Export Report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
