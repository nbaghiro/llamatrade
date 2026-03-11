/**
 * Animated Strategy Tree Preview
 * Shows a stylized preview of the visual strategy builder for empty states.
 * Uses CSS animations for a polished, engaging experience.
 */

import { Plus, Sparkles } from 'lucide-react';

interface StrategyTreePreviewProps {
  onCreateStrategy: () => void;
  onBrowseTemplates: () => void;
}

export function StrategyTreePreview({ onCreateStrategy, onBrowseTemplates }: StrategyTreePreviewProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center py-8 px-4">
      {/* Animated Tree Visualization */}
      <div className="relative mb-8">
        {/* Decorative glow behind the tree */}
        <div className="absolute inset-0 blur-3xl opacity-20 dark:opacity-30 bg-gradient-to-br from-violet-500 via-blue-500 to-emerald-500 rounded-full scale-75" />

        <svg
          width="320"
          height="200"
          viewBox="0 0 320 200"
          fill="none"
          className="relative z-10"
        >
          <defs>
            {/* Gradient for connecting lines */}
            <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#8b5cf6" />
              <stop offset="50%" stopColor="#3b82f6" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>

            {/* Glow filter */}
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Animated dash for flowing effect */}
            <style>
              {`
                @keyframes flowDown {
                  0% { stroke-dashoffset: 20; }
                  100% { stroke-dashoffset: 0; }
                }
                @keyframes fadeInUp {
                  0% { opacity: 0; transform: translateY(10px); }
                  100% { opacity: 1; transform: translateY(0); }
                }
                @keyframes pulse {
                  0%, 100% { opacity: 0.8; }
                  50% { opacity: 1; }
                }
                @keyframes countUp {
                  0% { opacity: 0; }
                  100% { opacity: 1; }
                }
                .line-animate {
                  stroke-dasharray: 5 3;
                  animation: flowDown 1s linear infinite;
                }
                .block-1 { animation: fadeInUp 0.5s ease-out 0.1s both; }
                .block-2 { animation: fadeInUp 0.5s ease-out 0.4s both; }
                .block-3 { animation: fadeInUp 0.5s ease-out 0.6s both; }
                .block-4 { animation: fadeInUp 0.5s ease-out 0.8s both; }
                .pulse { animation: pulse 2s ease-in-out infinite; }
                .percent { animation: countUp 0.3s ease-out 1s both; }
              `}
            </style>
          </defs>

          {/* Connecting Lines - drawn with gradient */}
          <g className="line-animate" stroke="url(#lineGradient)" strokeWidth="2" fill="none">
            {/* Root to children */}
            <path d="M160 55 L160 75 L80 75 L80 95" />
            <path d="M160 55 L160 95" />
            <path d="M160 55 L160 75 L240 75 L240 95" />
          </g>

          {/* Animated dots traveling along lines */}
          <circle r="3" fill="#3b82f6" className="pulse">
            <animateMotion dur="2s" repeatCount="indefinite" path="M160 55 L160 75 L80 75 L80 95" />
          </circle>
          <circle r="3" fill="#8b5cf6" className="pulse" style={{ animationDelay: '0.5s' }}>
            <animateMotion dur="2s" repeatCount="indefinite" path="M160 55 L160 95" />
          </circle>
          <circle r="3" fill="#10b981" className="pulse" style={{ animationDelay: '1s' }}>
            <animateMotion dur="2s" repeatCount="indefinite" path="M160 55 L160 75 L240 75 L240 95" />
          </circle>

          {/* Root Block - Portfolio */}
          <g className="block-1" filter="url(#glow)">
            <rect x="100" y="15" width="120" height="40" rx="8"
              className="fill-white dark:fill-gray-800 stroke-gray-200 dark:stroke-gray-700" strokeWidth="1.5" />
            <text x="160" y="32" textAnchor="middle" className="fill-gray-400 dark:fill-gray-500 text-[9px] font-medium">
              PORTFOLIO
            </text>
            <text x="160" y="46" textAnchor="middle" className="fill-gray-900 dark:fill-gray-100 text-[13px] font-bold percent">
              100%
            </text>
          </g>

          {/* Child Block 1 - Stocks */}
          <g className="block-2">
            <rect x="30" y="95" width="100" height="50" rx="8"
              className="fill-white dark:fill-gray-800 stroke-violet-300 dark:stroke-violet-700" strokeWidth="1.5" />
            <text x="80" y="113" textAnchor="middle" className="fill-violet-600 dark:fill-violet-400 text-[9px] font-medium">
              STOCKS
            </text>
            <text x="80" y="132" textAnchor="middle" className="fill-gray-900 dark:fill-gray-100 text-[16px] font-bold percent">
              60%
            </text>
          </g>

          {/* Child Block 2 - Bonds */}
          <g className="block-3">
            <rect x="140" y="95" width="80" height="50" rx="8"
              className="fill-white dark:fill-gray-800 stroke-blue-300 dark:stroke-blue-700" strokeWidth="1.5" />
            <text x="180" y="113" textAnchor="middle" className="fill-blue-600 dark:fill-blue-400 text-[9px] font-medium">
              BONDS
            </text>
            <text x="180" y="132" textAnchor="middle" className="fill-gray-900 dark:fill-gray-100 text-[16px] font-bold percent">
              30%
            </text>
          </g>

          {/* Child Block 3 - Gold */}
          <g className="block-4">
            <rect x="230" y="95" width="70" height="50" rx="8"
              className="fill-white dark:fill-gray-800 stroke-emerald-300 dark:stroke-emerald-700" strokeWidth="1.5" />
            <text x="265" y="113" textAnchor="middle" className="fill-emerald-600 dark:fill-emerald-400 text-[9px] font-medium">
              GOLD
            </text>
            <text x="265" y="132" textAnchor="middle" className="fill-gray-900 dark:fill-gray-100 text-[16px] font-bold percent">
              10%
            </text>
          </g>

          {/* Decorative sparkle */}
          <g className="pulse" style={{ animationDelay: '0.3s' }}>
            <circle cx="220" y="25" r="2" className="fill-amber-400" />
          </g>
        </svg>
      </div>

      {/* Text Content */}
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Design strategies visually
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
          Build portfolio allocations with our intuitive drag-and-drop builder. No code required.
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <button
          onClick={onCreateStrategy}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          Create Strategy
        </button>
        <button
          onClick={onBrowseTemplates}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg font-medium transition-colors"
        >
          <Sparkles className="w-4 h-4" />
          Browse Templates
        </button>
      </div>
    </div>
  );
}
