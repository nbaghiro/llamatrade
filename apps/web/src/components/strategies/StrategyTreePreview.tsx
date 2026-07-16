/**
 * Stylized, animated preview of the visual strategy builder shown in empty states.
 */

import { Plus, Sparkles } from 'lucide-react';

interface StrategyTreePreviewProps {
  onCreateStrategy: () => void;
  onBrowseTemplates: () => void;
}

export function StrategyTreePreview({ onCreateStrategy, onBrowseTemplates }: StrategyTreePreviewProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center py-8 px-4">
      <div className="relative mb-8">
        <div className="absolute inset-0 blur-3xl opacity-20 dark:opacity-30 bg-gradient-to-br from-orange-500 via-blue-500 to-green-600 rounded-full scale-75" />

        <svg
          width="320"
          height="200"
          viewBox="0 0 320 200"
          fill="none"
          className="relative z-10"
        >
          <defs>
            <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#ff4d1c" />
              <stop offset="50%" stopColor="#1a1aff" />
              <stop offset="100%" stopColor="#0f7a34" />
            </linearGradient>

            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

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

          <g className="line-animate" stroke="url(#lineGradient)" strokeWidth="2" fill="none">
            <path d="M160 55 L160 75 L80 75 L80 95" />
            <path d="M160 55 L160 95" />
            <path d="M160 55 L160 75 L240 75 L240 95" />
          </g>

          <circle r="3" fill="#1a1aff" className="pulse">
            <animateMotion dur="2s" repeatCount="indefinite" path="M160 55 L160 75 L80 75 L80 95" />
          </circle>
          <circle r="3" fill="#ff4d1c" className="pulse" style={{ animationDelay: '0.5s' }}>
            <animateMotion dur="2s" repeatCount="indefinite" path="M160 55 L160 95" />
          </circle>
          <circle r="3" fill="#0f7a34" className="pulse" style={{ animationDelay: '1s' }}>
            <animateMotion dur="2s" repeatCount="indefinite" path="M160 55 L160 75 L240 75 L240 95" />
          </circle>

          <g className="block-1" filter="url(#glow)">
            <rect x="100" y="15" width="120" height="40" rx="8"
              className="fill-paper stroke-ink" strokeWidth="2" />
            <text x="160" y="32" textAnchor="middle" className="fill-ink/60 text-[9px] font-mono uppercase tracking-wide">
              PORTFOLIO
            </text>
            <text x="160" y="46" textAnchor="middle" className="fill-ink text-[13px] font-mono font-bold percent">
              100%
            </text>
          </g>

          <g className="block-2">
            <rect x="30" y="95" width="100" height="50" rx="8"
              className="fill-paper stroke-orange-500" strokeWidth="2" />
            <text x="80" y="113" textAnchor="middle" className="fill-orange-600 text-[9px] font-mono uppercase tracking-wide">
              STOCKS
            </text>
            <text x="80" y="132" textAnchor="middle" className="fill-ink text-[16px] font-mono font-bold percent">
              60%
            </text>
          </g>

          <g className="block-3">
            <rect x="140" y="95" width="80" height="50" rx="8"
              className="fill-paper stroke-blue-500" strokeWidth="2" />
            <text x="180" y="113" textAnchor="middle" className="fill-blue-600 text-[9px] font-mono uppercase tracking-wide">
              BONDS
            </text>
            <text x="180" y="132" textAnchor="middle" className="fill-ink text-[16px] font-mono font-bold percent">
              30%
            </text>
          </g>

          <g className="block-4">
            <rect x="230" y="95" width="70" height="50" rx="8"
              className="fill-paper stroke-green-600" strokeWidth="2" />
            <text x="265" y="113" textAnchor="middle" className="fill-green-600 text-[9px] font-mono uppercase tracking-wide">
              GOLD
            </text>
            <text x="265" y="132" textAnchor="middle" className="fill-ink text-[16px] font-mono font-bold percent">
              10%
            </text>
          </g>

          <g className="pulse" style={{ animationDelay: '0.3s' }}>
            <circle cx="220" y="25" r="2" className="fill-orange-400" />
          </g>
        </svg>
      </div>

      <div className="text-center mb-6">
        <h3 className="text-lg font-display uppercase tracking-tight text-ink mb-2">
          Design strategies visually
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
          Build portfolio allocations with our intuitive drag-and-drop builder. No code required.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row items-center gap-3">
        <button
          onClick={onCreateStrategy}
          className="btn btn-primary btn-lg"
        >
          <Plus className="w-4 h-4" />
          Create Strategy
        </button>
        <button
          onClick={onBrowseTemplates}
          className="btn btn-ghost btn-lg"
        >
          <Sparkles className="w-4 h-4" />
          Browse Templates
        </button>
      </div>
    </div>
  );
}
