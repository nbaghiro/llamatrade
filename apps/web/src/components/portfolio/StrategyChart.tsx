/**
 * Strategy Performance Chart
 * Multi-line chart showing % returns for each strategy over time.
 * Includes interactive legend, benchmark line, and hover tooltips.
 */

import { ChevronDown } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { Benchmark, EquityPoint, Period, StrategyPerformance } from '../../store/portfolio';

interface StrategyChartProps {
  strategies: StrategyPerformance[];
  benchmarkData: EquityPoint[];
  selectedPeriod: Period;
  selectedBenchmark: Benchmark;
  visibleStrategyIds: Set<string>;
  hoveredStrategyId: string | null;
  onPeriodChange: (period: Period) => void;
  onBenchmarkChange: (benchmark: Benchmark) => void;
  onToggleVisibility: (id: string) => void;
  onHoverStrategy: (id: string | null) => void;
}

const PERIODS: Period[] = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'];
const BENCHMARKS: { value: Benchmark; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'SPY', label: 'SPY' },
  { value: 'QQQ', label: 'QQQ' },
  { value: 'IWM', label: 'IWM' },
  { value: 'DIA', label: 'DIA' },
];

const BENCHMARK_COLOR = '#9ca3af'; // gray-400

function formatDateShort(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDateFull(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export default function StrategyChart({
  strategies,
  benchmarkData,
  selectedPeriod,
  selectedBenchmark,
  visibleStrategyIds,
  hoveredStrategyId,
  onPeriodChange,
  onBenchmarkChange,
  onToggleVisibility,
  onHoverStrategy,
}: StrategyChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [showBenchmarkDropdown, setShowBenchmarkDropdown] = useState(false);

  // Filter to visible strategies
  const visibleStrategies = useMemo(
    () => strategies.filter((s) => visibleStrategyIds.has(s.id)),
    [strategies, visibleStrategyIds]
  );

  // Combine all data points to find chart bounds
  const chartBounds = useMemo(() => {
    const allValues: number[] = [];
    let maxLength = 0;

    visibleStrategies.forEach((s) => {
      s.equityCurve.forEach((p) => allValues.push(p.value));
      maxLength = Math.max(maxLength, s.equityCurve.length);
    });

    if (selectedBenchmark !== 'none') {
      benchmarkData.forEach((p) => allValues.push(p.value));
      maxLength = Math.max(maxLength, benchmarkData.length);
    }

    if (allValues.length === 0) {
      return { minValue: -10, maxValue: 10, dataLength: 30 };
    }

    const minValue = Math.min(...allValues, 0); // Always include 0
    const maxValue = Math.max(...allValues, 0);
    const padding = Math.max((maxValue - minValue) * 0.1, 2);

    return {
      minValue: minValue - padding,
      maxValue: maxValue + padding,
      dataLength: maxLength,
    };
  }, [visibleStrategies, benchmarkData, selectedBenchmark]);

  // Chart dimensions
  const width = 1000;
  const height = 320;
  const padding = { top: 30, right: 60, bottom: 50, left: 60 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Scale functions
  const xScale = (i: number) =>
    padding.left + (i / Math.max(chartBounds.dataLength - 1, 1)) * chartWidth;
  const yScale = (value: number) => {
    const range = chartBounds.maxValue - chartBounds.minValue;
    if (range === 0) return padding.top + chartHeight / 2;
    return padding.top + chartHeight - ((value - chartBounds.minValue) / range) * chartHeight;
  };

  // Y-axis ticks
  const yTicks = useMemo(() => {
    const tickCount = 5;
    const range = chartBounds.maxValue - chartBounds.minValue;
    const step = range / (tickCount - 1);
    return Array.from({ length: tickCount }, (_, i) => chartBounds.minValue + i * step);
  }, [chartBounds]);

  // X-axis ticks
  const xTicks = useMemo(() => {
    const dataLength = chartBounds.dataLength;
    if (dataLength <= 1) return [0];
    const count = Math.min(6, dataLength);
    const step = Math.floor((dataLength - 1) / (count - 1));
    return Array.from({ length: count }, (_, i) => Math.min(i * step, dataLength - 1));
  }, [chartBounds.dataLength]);

  // Generate line path for a strategy
  const getLinePath = (curve: EquityPoint[]) => {
    if (curve.length === 0) return '';
    return curve.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)},${yScale(p.value)}`).join(' ');
  };

  // Get date for x-axis label
  const getDateAtIndex = (index: number): Date => {
    // Use first visible strategy's data for dates
    const firstStrategy = visibleStrategies[0];
    if (firstStrategy && firstStrategy.equityCurve[index]) {
      return new Date(firstStrategy.equityCurve[index].timestamp);
    }
    // Fallback
    const date = new Date();
    date.setDate(date.getDate() - (chartBounds.dataLength - 1 - index));
    return date;
  };

  // Get tooltip data at hover index
  const tooltipData = useMemo(() => {
    if (hoveredIndex === null) return null;

    const date = getDateAtIndex(hoveredIndex);
    const values: { name: string; color: string; value: number }[] = [];

    visibleStrategies.forEach((s) => {
      const point = s.equityCurve[hoveredIndex];
      if (point) {
        values.push({
          name: s.name,
          color: s.color,
          value: point.value,
        });
      }
    });

    if (selectedBenchmark !== 'none' && benchmarkData[hoveredIndex]) {
      values.push({
        name: selectedBenchmark,
        color: BENCHMARK_COLOR,
        value: benchmarkData[hoveredIndex].value,
      });
    }

    return { date, values };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredIndex, visibleStrategies, benchmarkData, selectedBenchmark]);

  // Zero line Y position
  const zeroY = yScale(0);

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
      {/* Controls */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        {/* Period Selector */}
        <div className="flex gap-1">
          {PERIODS.map((period) => (
            <button
              key={period}
              onClick={() => onPeriodChange(period)}
              className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                selectedPeriod === period
                  ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              {period}
            </button>
          ))}
        </div>

        {/* Benchmark Selector */}
        <div className="relative">
          <button
            onClick={() => setShowBenchmarkDropdown(!showBenchmarkDropdown)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
          >
            <span className="text-xs text-gray-500">Benchmark:</span>
            <span className="font-medium">
              {selectedBenchmark === 'none' ? 'None' : selectedBenchmark}
            </span>
            <ChevronDown className="w-4 h-4" />
          </button>

          {showBenchmarkDropdown && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowBenchmarkDropdown(false)}
              />
              <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1 min-w-[100px]">
                {BENCHMARKS.map((b) => (
                  <button
                    key={b.value}
                    onClick={() => {
                      onBenchmarkChange(b.value);
                      setShowBenchmarkDropdown(false);
                    }}
                    className={`w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 ${
                      selectedBenchmark === b.value
                        ? 'text-green-600 dark:text-green-400 font-medium'
                        : 'text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="relative p-4">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto"
          preserveAspectRatio="xMidYMid meet"
          onMouseLeave={() => setHoveredIndex(null)}
        >
          {/* Grid lines */}
          {yTicks.map((tick, i) => (
            <line
              key={i}
              x1={padding.left}
              y1={yScale(tick)}
              x2={width - padding.right}
              y2={yScale(tick)}
              stroke="currentColor"
              strokeOpacity={tick === 0 ? 0.3 : 0.1}
              strokeWidth={tick === 0 ? 1 : 0.5}
              className="text-gray-400"
            />
          ))}

          {/* Zero line highlight */}
          <line
            x1={padding.left}
            y1={zeroY}
            x2={width - padding.right}
            y2={zeroY}
            stroke="currentColor"
            strokeOpacity={0.3}
            className="text-gray-500"
          />

          {/* Benchmark line */}
          {selectedBenchmark !== 'none' && benchmarkData.length > 0 && (
            <path
              d={getLinePath(benchmarkData)}
              fill="none"
              stroke={BENCHMARK_COLOR}
              strokeWidth="2"
              strokeDasharray="4 4"
              opacity={hoveredStrategyId ? 0.3 : 0.6}
            />
          )}

          {/* Strategy lines */}
          {visibleStrategies.map((strategy) => {
            const isHovered = hoveredStrategyId === strategy.id;
            const isDimmed = hoveredStrategyId && !isHovered;

            return (
              <path
                key={strategy.id}
                d={getLinePath(strategy.equityCurve)}
                fill="none"
                stroke={strategy.color}
                strokeWidth={isHovered ? 3 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={isDimmed ? 0.2 : 1}
                style={{ transition: 'opacity 0.15s, stroke-width 0.15s' }}
              />
            );
          })}

          {/* Y-axis labels */}
          {yTicks.map((tick, i) => (
            <text
              key={i}
              x={padding.left - 10}
              y={yScale(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-gray-400 text-[11px] font-data"
            >
              {tick >= 0 ? '+' : ''}
              {tick.toFixed(1)}%
            </text>
          ))}

          {/* X-axis labels */}
          {xTicks.map((idx) => (
            <text
              key={idx}
              x={xScale(idx)}
              y={height - padding.bottom + 20}
              textAnchor="middle"
              className="fill-gray-400 text-[11px]"
            >
              {formatDateShort(getDateAtIndex(idx))}
            </text>
          ))}

          {/* Invisible hover targets */}
          {Array.from({ length: chartBounds.dataLength }).map((_, i) => (
            <rect
              key={i}
              x={xScale(i) - chartWidth / chartBounds.dataLength / 2}
              y={padding.top}
              width={chartWidth / chartBounds.dataLength}
              height={chartHeight}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(i)}
            />
          ))}

          {/* Hover crosshair */}
          {hoveredIndex !== null && (
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
          )}

          {/* Hover dots */}
          {hoveredIndex !== null &&
            visibleStrategies.map((strategy) => {
              const point = strategy.equityCurve[hoveredIndex];
              if (!point) return null;
              return (
                <circle
                  key={strategy.id}
                  cx={xScale(hoveredIndex)}
                  cy={yScale(point.value)}
                  r="5"
                  fill={strategy.color}
                  stroke="white"
                  strokeWidth="2"
                />
              );
            })}
        </svg>

        {/* Tooltip */}
        {tooltipData && hoveredIndex !== null && (
          <div
            className="absolute bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 pointer-events-none z-10"
            style={{
              left: `${((xScale(hoveredIndex) / width) * 100).toFixed(1)}%`,
              top: '40px',
              transform: 'translateX(-50%)',
            }}
          >
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
              {formatDateFull(tooltipData.date)}
            </p>
            <div className="space-y-1.5">
              {tooltipData.values.map((v, i) => (
                <div key={i} className="flex items-center justify-between gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: v.color }}
                    />
                    <span className="text-gray-600 dark:text-gray-400">{v.name}</span>
                  </div>
                  <span
                    className={`font-mono font-medium ${
                      v.value >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {formatPercent(v.value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 pb-4 flex-wrap">
        {strategies.map((strategy) => {
          const isVisible = visibleStrategyIds.has(strategy.id);
          const isHovered = hoveredStrategyId === strategy.id;

          return (
            <button
              key={strategy.id}
              onClick={() => onToggleVisibility(strategy.id)}
              onMouseEnter={() => onHoverStrategy(strategy.id)}
              onMouseLeave={() => onHoverStrategy(null)}
              className={`flex items-center gap-2 px-2 py-1 rounded transition-all ${
                isVisible
                  ? 'opacity-100'
                  : 'opacity-40'
              } ${isHovered ? 'bg-gray-100 dark:bg-gray-800' : ''}`}
            >
              <div
                className="w-3 h-3 rounded-full"
                style={{
                  backgroundColor: isVisible ? strategy.color : 'transparent',
                  border: `2px solid ${strategy.color}`,
                }}
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">{strategy.name}</span>
            </button>
          );
        })}

        {selectedBenchmark !== 'none' && (
          <div className="flex items-center gap-2 px-2 py-1">
            <div className="w-3 h-0 border-t-2 border-dashed border-gray-400" />
            <span className="text-sm text-gray-500">{selectedBenchmark}</span>
          </div>
        )}
      </div>
    </div>
  );
}
