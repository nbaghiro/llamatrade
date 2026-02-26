import { ChevronDown, Play } from 'lucide-react';
import { useState } from 'react';

export function RightPanel() {
  const [isPreviewOpen, setIsPreviewOpen] = useState(true);

  return (
    <div className="w-[420px] flex-shrink-0 flex flex-col gap-3 p-4 overflow-y-auto">
      {/* Backtest Preview */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
        <button
          onClick={() => setIsPreviewOpen(!isPreviewOpen)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Backtest Preview</span>
          <ChevronDown
            className={`w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform ${
              isPreviewOpen ? '' : '-rotate-90'
            }`}
          />
        </button>

        {isPreviewOpen && (
          <div className="px-3 pb-3">
            {/* Chart */}
            <div className="h-40 bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 mb-3 p-2">
              <svg viewBox="0 0 200 80" className="w-full h-full" preserveAspectRatio="none">
                {/* Grid lines */}
                <g stroke="#e5e5e5" strokeWidth="0.5">
                  <line x1="0" y1="20" x2="200" y2="20" />
                  <line x1="0" y1="40" x2="200" y2="40" />
                  <line x1="0" y1="60" x2="200" y2="60" />
                </g>

                {/* Benchmark line (gray) */}
                <path
                  d="M 0 50 Q 20 48, 40 52 T 80 48 T 120 45 T 160 42 T 200 38"
                  fill="none"
                  stroke="#9ca3af"
                  strokeWidth="1.5"
                  strokeDasharray="4 2"
                />

                {/* Strategy line (green) - more complex with volatility */}
                <path
                  d="M 0 55
                     C 10 52, 15 58, 25 50
                     C 35 42, 40 48, 50 44
                     C 60 40, 65 35, 75 38
                     C 85 41, 90 32, 100 28
                     C 110 24, 115 30, 125 25
                     C 135 20, 140 18, 150 22
                     C 160 26, 165 15, 175 12
                     C 185 9, 190 14, 200 8"
                  fill="none"
                  stroke="#22c55e"
                  strokeWidth="2"
                />

                {/* Area fill under strategy line */}
                <path
                  d="M 0 55
                     C 10 52, 15 58, 25 50
                     C 35 42, 40 48, 50 44
                     C 60 40, 65 35, 75 38
                     C 85 41, 90 32, 100 28
                     C 110 24, 115 30, 125 25
                     C 135 20, 140 18, 150 22
                     C 160 26, 165 15, 175 12
                     C 185 9, 190 14, 200 8
                     V 80 H 0 Z"
                  fill="url(#areaGradient)"
                  opacity="0.3"
                />

                <defs>
                  <linearGradient id="areaGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                  </linearGradient>
                </defs>
              </svg>
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center gap-4 mb-3 text-xs">
              <div className="flex items-center gap-1.5">
                <div className="w-4 h-0.5 bg-primary-500 rounded" />
                <span className="text-gray-600 dark:text-gray-400">Strategy</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div
                  className="w-4 h-0.5 bg-gray-400 rounded"
                  style={{
                    backgroundImage:
                      'repeating-linear-gradient(90deg, #9ca3af 0, #9ca3af 4px, transparent 4px, transparent 6px)',
                  }}
                />
                <span className="text-gray-600 dark:text-gray-400">SPY</span>
              </div>
            </div>

            {/* Run button */}
            <button className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 text-green-700 dark:text-green-400 font-medium transition-colors border border-green-200 dark:border-green-800">
              <Play className="w-4 h-4 fill-current" />
              <span className="text-sm">RUN</span>
            </button>

            {/* Jump to backtest */}
            <button className="w-full flex items-center justify-center gap-1 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors mt-1">
              <span>→</span>
              <span>Jump to Backtest</span>
            </button>
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Quick Stats</h3>
        <div className="space-y-2.5 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">CAGR</span>
            <span className="text-gray-900 dark:text-gray-100 font-medium">--</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Max Drawdown</span>
            <span className="text-gray-900 dark:text-gray-100 font-medium">--</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Sharpe Ratio</span>
            <span className="text-gray-900 dark:text-gray-100 font-medium">--</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Volatility</span>
            <span className="text-gray-900 dark:text-gray-100 font-medium">--</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Win Rate</span>
            <span className="text-gray-900 dark:text-gray-100 font-medium">--</span>
          </div>
        </div>
      </div>
    </div>
  );
}
