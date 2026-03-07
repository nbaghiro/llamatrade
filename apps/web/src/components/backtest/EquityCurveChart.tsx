/**
 * Equity Curve Chart Component
 * Shows equity curve over time with drawdown visualization.
 * Uses custom SVG for zero dependencies.
 */

import { useMemo, useState } from 'react';

import type { EquityPoint } from '../../generated/proto/backtest_pb';
import { toDate, toNumber } from '../../store/backtest';

interface EquityCurveChartProps {
  data: EquityPoint[];
  initialCapital: number;
  showDrawdown?: boolean;
}

interface ChartDataPoint {
  date: Date;
  equity: number;
  drawdown: number;
  dailyReturn: number;
}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
}

function formatDateShort(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDateFull(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function EquityCurveChart({
  data,
  initialCapital,
}: EquityCurveChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartData = useMemo<ChartDataPoint[]>(() => {
    return data.map((point) => {
      const date = toDate(point.timestamp);
      return {
        date: date ?? new Date(),
        equity: toNumber(point.equity),
        drawdown: toNumber(point.drawdown),
        dailyReturn: toNumber(point.dailyReturn),
      };
    });
  }, [data]);

  const { minEquity, maxEquity } = useMemo(() => {
    if (chartData.length === 0) {
      return { minEquity: initialCapital * 0.8, maxEquity: initialCapital * 1.2 };
    }
    const equities = chartData.map((d) => d.equity);
    const min = Math.min(...equities);
    const max = Math.max(...equities);
    const pad = (max - min) * 0.1 || max * 0.1;
    return {
      minEquity: min - pad,
      maxEquity: max + pad,
    };
  }, [chartData, initialCapital]);

  // Y-axis ticks - must be before early return
  const yTicks = useMemo(() => {
    const tickCount = 5;
    const range = maxEquity - minEquity;
    const step = range / (tickCount - 1);
    return Array.from({ length: tickCount }, (_, i) => minEquity + i * step);
  }, [minEquity, maxEquity]);

  // X-axis ticks (show ~5 dates) - must be before early return
  const xTicks = useMemo(() => {
    if (chartData.length <= 1) return [0];
    const count = Math.min(5, chartData.length);
    const step = Math.floor((chartData.length - 1) / (count - 1));
    return Array.from({ length: count }, (_, i) => Math.min(i * step, chartData.length - 1));
  }, [chartData.length]);

  if (chartData.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <div className="flex items-center justify-center h-64 text-gray-400 dark:text-gray-500">
          No equity data available
        </div>
      </div>
    );
  }

  const finalEquity = chartData[chartData.length - 1]?.equity ?? initialCapital;
  const isPositive = finalEquity >= initialCapital;

  // Chart dimensions
  const width = 800;
  const height = 300;
  const padding = { top: 20, right: 60, bottom: 40, left: 70 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Scale functions
  const xScale = (i: number) => padding.left + (i / (chartData.length - 1)) * chartWidth;
  const yScale = (equity: number) =>
    padding.top + chartHeight - ((equity - minEquity) / (maxEquity - minEquity)) * chartHeight;

  // Generate path
  const linePath = chartData
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)},${yScale(d.equity)}`)
    .join(' ');

  const areaPath = `${linePath} L ${xScale(chartData.length - 1)},${height - padding.bottom} L ${padding.left},${height - padding.bottom} Z`;

  // Initial capital line Y position
  const initialCapitalY = yScale(initialCapital);

  // Hovered point
  const hoveredPoint = hoveredIndex !== null ? chartData[hoveredIndex] : null;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-gray-900 dark:text-gray-100">Equity Curve</h3>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-0.5 ${isPositive ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-500 dark:text-gray-400">Equity</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-0 border-t border-dashed border-gray-400" />
            <span className="text-gray-500 dark:text-gray-400">Initial</span>
          </div>
        </div>
      </div>

      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto"
          preserveAspectRatio="xMidYMid meet"
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={isPositive ? '#22c55e' : '#ef4444'} stopOpacity="0.2" />
              <stop offset="100%" stopColor={isPositive ? '#22c55e' : '#ef4444'} stopOpacity="0.02" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {yTicks.map((tick, i) => (
            <line
              key={i}
              x1={padding.left}
              y1={yScale(tick)}
              x2={width - padding.right}
              y2={yScale(tick)}
              stroke="currentColor"
              strokeOpacity={0.1}
              className="text-gray-400"
            />
          ))}

          {/* Initial capital reference line */}
          <line
            x1={padding.left}
            y1={initialCapitalY}
            x2={width - padding.right}
            y2={initialCapitalY}
            stroke="currentColor"
            strokeDasharray="4 4"
            strokeOpacity={0.5}
            className="text-gray-400"
          />

          {/* Area fill */}
          <path d={areaPath} fill="url(#equityGradient)" />

          {/* Line */}
          <path
            d={linePath}
            fill="none"
            stroke={isPositive ? '#22c55e' : '#ef4444'}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Y-axis labels */}
          {yTicks.map((tick, i) => (
            <text
              key={i}
              x={padding.left - 10}
              y={yScale(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-gray-400 text-[10px]"
            >
              {formatCurrency(tick)}
            </text>
          ))}

          {/* X-axis labels */}
          {xTicks.map((idx) => (
            <text
              key={idx}
              x={xScale(idx)}
              y={height - padding.bottom + 20}
              textAnchor="middle"
              className="fill-gray-400 text-[10px]"
            >
              {formatDateShort(chartData[idx].date)}
            </text>
          ))}

          {/* Invisible hover targets */}
          {chartData.map((_, i) => (
            <rect
              key={i}
              x={xScale(i) - chartWidth / chartData.length / 2}
              y={padding.top}
              width={chartWidth / chartData.length}
              height={chartHeight}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(i)}
            />
          ))}

          {/* Hover indicator */}
          {hoveredIndex !== null && (
            <>
              <line
                x1={xScale(hoveredIndex)}
                y1={padding.top}
                x2={xScale(hoveredIndex)}
                y2={height - padding.bottom}
                stroke="currentColor"
                strokeOpacity={0.3}
                strokeDasharray="2 2"
                className="text-gray-500"
              />
              <circle
                cx={xScale(hoveredIndex)}
                cy={yScale(chartData[hoveredIndex].equity)}
                r="5"
                fill={isPositive ? '#22c55e' : '#ef4444'}
                stroke="white"
                strokeWidth="2"
              />
            </>
          )}
        </svg>

        {/* Tooltip */}
        {hoveredPoint && hoveredIndex !== null && (
          <div
            className="absolute bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 pointer-events-none z-10"
            style={{
              left: `${((xScale(hoveredIndex) / width) * 100).toFixed(1)}%`,
              top: '10px',
              transform: 'translateX(-50%)',
            }}
          >
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
              {formatDateFull(hoveredPoint.date)}
            </p>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between gap-4">
                <span className="text-gray-500 dark:text-gray-400">Equity:</span>
                <span className="font-mono text-gray-900 dark:text-gray-100">
                  {formatCurrency(hoveredPoint.equity)}
                </span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-gray-500 dark:text-gray-400">Daily Return:</span>
                <span
                  className={`font-mono ${hoveredPoint.dailyReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}
                >
                  {hoveredPoint.dailyReturn >= 0 ? '+' : ''}
                  {(hoveredPoint.dailyReturn * 100).toFixed(2)}%
                </span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-gray-500 dark:text-gray-400">Drawdown:</span>
                <span className="font-mono text-red-600 dark:text-red-400">
                  {(hoveredPoint.drawdown * 100).toFixed(2)}%
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
